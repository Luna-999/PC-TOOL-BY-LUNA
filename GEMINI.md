# OP TOOL v2.0 — Project Instructions

## Architecture Overview
OP TOOL has migrated from a Flask/Web architecture to a **Native CustomTkinter GUI** (v2.0).

### Key Architectural Principles
- **Native GUI**: Uses `customtkinter` for a modern, high-performance Windows interface.
- **Standalone Data Layer**: `db.py` handles all SQLite operations directly (no Flask-SQLAlchemy).
- **Bridge Pattern**: `bridge/windows_bridge.py` provides a clean interface for Windows-specific operations (Registry, Services, WMI, DPC).
- **Atomic Registry Writes**: Use `reg_write_tracked()` in `windows_bridge.py` for all reversible changes. This ensures every write is preceded by a log entry in the `change_log` table.
- **Global Event Bus**: `gui_app.py` implements a publish/subscribe system for cross-tab communication.
- **Persistent Tabs**: Tabs use `pack_forget()` for navigation instead of `destroy()`. This allows background threads (like DPC scans) to survive tab switching.
- **Single Polling Thread**: The main app owns a single background thread that publishes a `system_snapshot` event every 2 seconds.

## Workflows & Conventions

### Adding New Registry Optimizations
1. Define the optimization in `bridge/windows_bridge.py`.
2. **MUST** use `reg_write_tracked()` to ensure the change can be reverted via the Restore tab.
3. Use descriptive `change_type` names (e.g., "msi", "affinity").

### tab Development
- All tabs should inherit from `ctk.CTkFrame` (or a helper class if one is created).
- Subscribe to `system_snapshot` if live system data is needed.
- Publish events (e.g., `profile_applied`) if a change affects other tabs.

### Error Handling
- Use the Step-by-Step feedback pattern (see `gui/tabs/profiles.py`) for long-running operations.
- Implement automatic rollback on partial failures for critical sequences.

## Known Limitations & TODOs
- VID/PID lookup for controller polling rates is currently limited to 9 known IDs.
- DPC column discovery is fuzzy; localized Windows versions may need testing.
- CTF restoration currently defaults to `SERVICE_AUTO_START`.
