"""
OP TOOL — Transactional Ledger for Registry Changes.
Now uses the standalone db.py (no Flask/SQLAlchemy).
"""
import winreg
from datetime import datetime
import db

def new_session():
    return db.new_session()


def get_session():
    return db.get_session()


def record(change_type, reg_path, value_name, original_value,
           applied_value, device_id=None, profile_name=None):
    """
    Record a change BEFORE writing to the registry.
    This is the source of truth for the restore system.
    """
    return db.record_change(
        change_type, reg_path, value_name, original_value,
        applied_value, device_id, profile_name
    )


def restore_session(session_id):
    """
    Revert all changes from a session in REVERSE order (last-in first-out).
    Reads original values from change_log and rewrites them.
    """
    from bridge.windows_bridge import reg_write

    entries = db.get_session_changes(session_id)
    results = []

    for entry in entries:
        # Re-convert stored string values back to their original types
        try:
            val_str = entry['original_value']
            if entry['change_type'] == 'affinity_binary':
                original = bytes.fromhex(val_str)
                reg_type = winreg.REG_BINARY
            else:
                # Most registry values we touch are DWORDS (integers)
                original = int(val_str)
                reg_type = winreg.REG_DWORD
        except Exception:
            # Fallback for unexpected types
            original = entry['original_value']
            reg_type = winreg.REG_SZ

        ok = reg_write(winreg.HKEY_LOCAL_MACHINE, entry['reg_path'],
                       entry['reg_value_name'], original, reg_type)
        
        if ok:
            db.mark_restored(entry['id'])
            
        results.append({"entry_id": entry['id'], "success": ok})

    return {
        "session_id": session_id,
        "results": results,
        "total": len(results),
        "succeeded": sum(1 for r in results if r["success"])
    }
