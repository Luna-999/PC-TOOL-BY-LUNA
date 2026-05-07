# OP TOOL v2.0 — Comprehensive Technical Documentation

This document serves as the exhaustive record of the **OP TOOL v2.0 Native Migration**. It details every architectural change, implementation strategy, and security measure taken to transform the project from a "UI web app" into a "real standalone EXE" native desktop application.

---

## 1. Executive Summary of Changes
The v2.0 update focused on **Total De-Webbing** and **Native Consolidation**:
- **Removed:** All Flask, SQLAlchemy, Jinja2, and Web-related assets (CSS/JS).
- **Implemented:** A high-performance, modular GUI built with `customtkinter`.
- **Refactored:** The database layer into a standalone SQLite implementation (`db.py`) to eliminate server-client overhead.
- **Unified:** The core OS "Bridge" logic directly into the native event loop.
- **Compiled:** A single-entry point executable with UAC Admin elevation enforced.

---

## 2. Detailed Architecture & File Map

### **Project Root**
- `run.py`: The primary entry point. It checks for Administrator privileges using `ctypes` and re-launches with elevation if necessary.
- `gui_app.py`: The native GUI shell. It manages the sidebar navigation and frame-swapping logic for the 10 optimization tabs.
- `db.py`: The source of truth for all data. Uses `sqlite3` in WAL (Write-Ahead Logging) mode for thread-safe access from the GUI and background polling threads.
- `optool.spec`: Custom PyInstaller build configuration set to `console=False` and `uac_admin=True`.

### **Core Modules**
- `gui/theme.py`: A centralized design system using `customtkinter` widget factories for a consistent, dark-themed aesthetic.
- `gui/tabs/`: Modular directory containing individual UI logic for Dashboard, DPC Latency, MSI/Devices, CPU Affinity, HID Controllers, and more.
- `bridge/windows_bridge.py`: The low-level OS interface. Handles `ntdll.dll` timer resolution, Registry manipulation via `winreg`, and PowerShell-based ETW tracing.
- `bridge/change_log.py`: The transactional safety layer.

---

## 3. Implementation Deep-Dive

### **A. Transitioning from Web to Native (How it was done)**
1.  **Dependency Purge:** Removed `flask`, `flask-sqlalchemy`, and `flask-cors`.
2.  **Database Migration:** Rewrote the data layer from SQLAlchemy Models to raw SQL in `db.py`. This ensures zero startup delay and zero dependency on a local "server" context.
3.  **UI Replacement:** Replaced HTML/Tailwind templates with `customtkinter` frames. This provides a truly hardware-accelerated interface that feels like a Windows 11 system utility.

### **B. Transactional Registry Ledger (The Safety Net)**
Registry changes are dangerous. To ensure 100% stability, I implemented a **LIFO (Last-In-First-Out) Restoration System**:
- **Recording:** Before a registry key is modified (e.g., forcing MSI mode), `bridge.change_log.record()` reads the current value from the system and stores it as a "Original Value" in the SQLite `change_log` table.
- **Restoration:** The `RestoreTab` queries these sessions. When a user clicks "Revert", the system reads the original binary or DWORD data and writes it back, then marks the change as "restored" in the DB.

### **C. Live DPC Latency Engine**
Unlike web apps that simulate data, OP TOOL v2.0 uses **Real-Time ETW Tracing**:
- **Mechanism:** The application spawns a background thread that invokes `wpr.exe` (Windows Performance Recorder).
- **Processing:** It captures driver execution times, processes the `.etl` trace into a CSV, and parses it to identify "latency spikes" (Severity: Critical if >500µs).
- **Visualization:** Data is saved to the SQLite `dpc_samples` table and rendered in a live list.

### **D. Hardware Timer Resolution**
Standard Windows timers oscillate at 15.6ms. OP TOOL v2.0 forces a 0.5ms (500µs) resolution:
- **How:** It uses `ntdll.dll` via `ctypes` to call the undocumented `NtSetTimerResolution` function.
- **Persistence:** The `run.py` entry point ensures this is set only while the app or an optimization profile is active.

---

## 4. Security & System Integrity

1.  **Mandatory UAC Elevation:** The app will not run as a standard user. This is enforced via `ctypes.windll.shell32.IsUserAnAdmin()`.
2.  **System Restore Integration:** Before applying any major hardware profile, the `bridge` executes a PowerShell script to create a **Windows System Restore Point**. If the restore point fails to create, the optimization is blocked.
3.  **Isolation:** No internet access is required. All operations are local to the machine, ensuring privacy and speed.

---

## 5. Build & Deployment Strategy

To create the "real exe", I used **PyInstaller 6.x** with the following specific configurations:
- **Windowed Mode:** `console=False` hides the black CMD window.
- **UAC Manifest:** `uac_admin=True` embeds the "Shield" icon on the EXE, forcing Windows to ask for Admin permission immediately.
- **Hidden Imports:** Manually added `win32timezone` and `PIL._tkinter_finder` to the spec file to resolve common PyInstaller bundling issues with native libraries.
- **Optimization:** Used `UPX` compression to keep the final EXE size small and fast to load.

---

## 6. How to Build (For Developers)
1. Install dependencies: `pip install -r requirements.txt`
2. Run build: `python -m PyInstaller optool.spec`
3. Result is found in: `dist/OPTOOL/OPTOOL.exe`

*Documentation generated following the v2.0 Native Migration.*
