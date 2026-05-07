"""
OP TOOL — Standalone SQLite data layer (no Flask dependency).
Data is stored in C:\\ProgramData\\OPTOOL\\optool.db
"""
import json
import os
import sqlite3
import uuid
from datetime import datetime

DATA_DIR = os.path.join(os.environ.get('PROGRAMDATA', r'C:\ProgramData'), 'OPTOOL')
DB_PATH = os.path.join(DATA_DIR, 'optool.db')
SETTINGS_FILE = os.path.join(DATA_DIR, 'settings.json')
LOG_DIR = os.path.join(DATA_DIR, 'logs')

_conn: sqlite3.Connection | None = None


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        os.makedirs(DATA_DIR, exist_ok=True)
        os.makedirs(LOG_DIR, exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
    return _conn


def init_db():
    """Create all tables if they don't exist."""
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            msi_enabled INTEGER DEFAULT 0,
            ctf_suppressed INTEGER DEFAULT 0,
            timer_resolution_100ns INTEGER DEFAULT 10000,
            affinity_game_cores TEXT,
            affinity_usb_core TEXT,
            affinity_nic_core TEXT,
            auto_apply_exe TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS change_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            profile_name TEXT,
            change_type TEXT NOT NULL,
            device_id TEXT,
            reg_path TEXT NOT NULL,
            reg_value_name TEXT NOT NULL,
            original_value TEXT,
            applied_value TEXT,
            restored INTEGER DEFAULT 0,
            applied_at TEXT DEFAULT (datetime('now')),
            restored_at TEXT
        );
        CREATE TABLE IF NOT EXISTS dpc_samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sample_time TEXT DEFAULT (datetime('now')),
            driver_name TEXT NOT NULL,
            avg_us REAL NOT NULL,
            max_us REAL NOT NULL,
            std_dev_us REAL NOT NULL,
            frequency INTEGER NOT NULL,
            severity TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS controllers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_path TEXT NOT NULL,
            friendly_name TEXT,
            vid TEXT,
            pid TEXT,
            connection_type TEXT,
            polling_rate_hz INTEGER,
            xinput_capped INTEGER DEFAULT 0,
            recommended_api TEXT,
            detected_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS restore_points (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sequence_number INTEGER NOT NULL,
            description TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            verified INTEGER DEFAULT 0
        );
    """)
    conn.commit()


# ─── Session tracking ───────────────────────────────
_current_session_id: str | None = None


def new_session() -> str:
    global _current_session_id
    _current_session_id = str(uuid.uuid4())[:8]
    return _current_session_id


def get_session() -> str:
    global _current_session_id
    if not _current_session_id:
        return new_session()
    return _current_session_id


# ─── Change log ─────────────────────────────────────

def record_change(change_type, reg_path, value_name, original_value,
                  applied_value, device_id=None, profile_name=None):
    conn = _get_conn()
    conn.execute(
        """INSERT INTO change_log
           (session_id, profile_name, change_type, device_id,
            reg_path, reg_value_name, original_value, applied_value, restored)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)""",
        (get_session(), profile_name, change_type, device_id,
         reg_path, value_name, str(original_value), str(applied_value))
    )
    conn.commit()


def get_active_changes():
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM change_log WHERE restored=0 ORDER BY applied_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def get_active_change_count():
    conn = _get_conn()
    row = conn.execute("SELECT COUNT(*) as cnt FROM change_log WHERE restored=0").fetchone()
    return row['cnt'] if row else 0


def get_active_sessions():
    """Group active changes by session for the restore UI."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM change_log WHERE restored=0 ORDER BY applied_at DESC"
    ).fetchall()
    sessions = {}
    for r in rows:
        r = dict(r)
        sid = r['session_id']
        if sid not in sessions:
            sessions[sid] = {
                'session_id': sid,
                'applied_at': r['applied_at'],
                'profile_name': r['profile_name'],
                'changes': []
            }
        sessions[sid]['changes'].append(r)
    return list(sessions.values())


def mark_restored(entry_id):
    conn = _get_conn()
    conn.execute(
        "UPDATE change_log SET restored=1, restored_at=? WHERE id=?",
        (datetime.utcnow().isoformat(), entry_id)
    )
    conn.commit()


def get_session_changes(session_id):
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM change_log WHERE session_id=? AND restored=0 ORDER BY id DESC",
        (session_id,)
    ).fetchall()
    return [dict(r) for r in rows]


# ─── Profiles ───────────────────────────────────────

def get_profiles():
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM profiles ORDER BY name").fetchall()
    return [dict(r) for r in rows]


def get_profile(pid):
    conn = _get_conn()
    row = conn.execute("SELECT * FROM profiles WHERE id=?", (pid,)).fetchone()
    return dict(row) if row else None


def create_profile(name, description='', msi_enabled=0, ctf_suppressed=0,
                   timer_resolution_100ns=10000, affinity_game_cores=None,
                   affinity_usb_core=None, affinity_nic_core=None,
                   auto_apply_exe=None):
    conn = _get_conn()
    conn.execute(
        """INSERT INTO profiles
           (name, description, msi_enabled, ctf_suppressed,
            timer_resolution_100ns, affinity_game_cores,
            affinity_usb_core, affinity_nic_core, auto_apply_exe)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (name, description, msi_enabled, ctf_suppressed,
         timer_resolution_100ns, affinity_game_cores,
         affinity_usb_core, affinity_nic_core, auto_apply_exe)
    )
    conn.commit()


def delete_profile(pid):
    conn = _get_conn()
    conn.execute("DELETE FROM profiles WHERE id=?", (pid,))
    conn.commit()


# ─── DPC samples ────────────────────────────────────

def save_dpc_samples(results):
    conn = _get_conn()
    for r in results:
        conn.execute(
            """INSERT INTO dpc_samples
               (driver_name, avg_us, max_us, std_dev_us, frequency, severity)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (r['driver_name'], r['avg_us'], r['max_us'],
             r['std_dev_us'], r['frequency'], r['severity'])
        )
    conn.commit()


def get_dpc_samples(limit=500):
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM dpc_samples ORDER BY sample_time DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


def clear_dpc_samples():
    conn = _get_conn()
    conn.execute("DELETE FROM dpc_samples")
    conn.commit()


# ─── Controllers ────────────────────────────────────

def save_controllers(controllers):
    conn = _get_conn()
    conn.execute("DELETE FROM controllers")
    for c in controllers:
        conn.execute(
            """INSERT INTO controllers
               (device_path, friendly_name, vid, pid,
                connection_type, polling_rate_hz, xinput_capped, recommended_api)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (c['device_path'], c['friendly_name'], c['vid'], c['pid'],
             c['connection_type'], c['polling_rate_hz'],
             c['xinput_capped'], c['recommended_api'])
        )
    conn.commit()


def get_controllers():
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM controllers").fetchall()
    return [dict(r) for r in rows]


# ─── Restore points ────────────────────────────────

def save_restore_point(sequence_number, description, verified=1):
    conn = _get_conn()
    conn.execute(
        "INSERT INTO restore_points (sequence_number, description, verified) VALUES (?, ?, ?)",
        (sequence_number, description, verified)
    )
    conn.commit()


def get_restore_points():
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM restore_points ORDER BY created_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


# ─── Settings (JSON) ───────────────────────────────

SETTINGS_DEFAULTS = {
    "dpc_interval_ms": 500,
    "history_days": 7,
    "alert_threshold_us": 500,
    "start_on_boot": False,
    "run_as_service": False,
    "show_tray": False,
    "launch_minimized": False,
}


def load_settings():
    data = dict(SETTINGS_DEFAULTS)
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r') as f:
                data.update(json.load(f))
        except Exception:
            pass
    return data


def save_settings(updates):
    current = load_settings()
    current.update(updates)
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(current, f, indent=2)


# ─── Timer Measurements ────────────────────────────

def save_timer_measurement(result: dict):
    """Save a timer measurement result to the database."""
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS timer_measurements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            measured_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            effective_resolution_ms REAL,
            reported_resolution_ms REAL,
            avg_overshoot_ms REAL,
            max_overshoot_ms REAL,
            std_dev_ms REAL,
            accuracy_percent REAL,
            grade TEXT,
            iterations INTEGER
        )
    """)
    conn.execute("""
        INSERT INTO timer_measurements
        (effective_resolution_ms, reported_resolution_ms, avg_overshoot_ms,
         max_overshoot_ms, std_dev_ms, accuracy_percent, grade, iterations)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        result.get("effective_resolution_ms", 0),
        result.get("reported_resolution_ms", 0),
        result.get("avg_overshoot_ms", 0),
        result.get("max_overshoot_ms", 0),
        result.get("std_dev_ms", 0),
        result.get("accuracy_percent", 0),
        result.get("grade", ""),
        result.get("iterations", 0)
    ))
    conn.commit()
