import winreg
import ctypes
import subprocess
import logging
import json
import os
import csv
import time
import tempfile

import win32serviceutil
import win32service
import psutil
import numpy as np
from ctypes import wintypes

logger = logging.getLogger("optool.bridge")

# ─────────────────────────────────────
# REGISTRY BRIDGE (winreg)
# ─────────────────────────────────────

def reg_read(hive, path, value_name):
    """Read a registry value. Returns (data, type) or (None, None) if missing."""
    try:
        key = winreg.OpenKey(hive, path, 0, winreg.KEY_READ)
        data, reg_type = winreg.QueryValueEx(key, value_name)
        winreg.CloseKey(key)
        return data, reg_type
    except FileNotFoundError:
        return None, None
    except Exception as e:
        logger.error(f"reg_read failed {path}\\{value_name}: {e}")
        return None, None


def reg_write(hive, path, value_name, data, reg_type=winreg.REG_DWORD):
    """
    Write a registry value. Creates key path if it does not exist.
    ALWAYS call change_log.record() before calling this function.
    Returns True on success.
    """
    try:
        key = winreg.CreateKeyEx(hive, path, 0, winreg.KEY_WRITE)
        winreg.SetValueEx(key, value_name, 0, reg_type, data)
        winreg.CloseKey(key)
        logger.info(f"reg_write: {path}\\{value_name} = {data}")
        return True
    except PermissionError:
        logger.error("reg_write: Access denied. OP TOOL must run as Administrator.")
        return False
    except Exception as e:
        logger.error(f"reg_write failed {path}\\{value_name}: {e}")
        return False


def reg_write_tracked(hive, path, value_name, new_data,
                      reg_type=winreg.REG_DWORD,
                      change_type="registry",
                      device_id=None,
                      profile_name=None):
    """
    Read original → log to change_log → write new value.
    Use this instead of reg_write() for any change that needs to be reversible.
    (OPT 4)
    """
    from bridge.change_log import record as clog_record

    # Always read original first
    original, _ = reg_read(hive, path, value_name)
    original_stored = original if original is not None else 0

    # Log before writing (BUG 1, 2, 3 fix via centralization)
    clog_record(change_type, path, value_name,
                original_value=original_stored,
                applied_value=new_data,
                device_id=device_id,
                profile_name=profile_name)

    # Write
    return reg_write(hive, path, value_name, new_data, reg_type)


def enable_msi(device_instance_id, vector_count=1):
    """
    Enable MSI interrupt mode for a PCI device.
    Uses reg_write_tracked to ensure restoration works (BUG 1).
    """
    reg_path = (
        f"SYSTEM\\CurrentControlSet\\Enum\\{device_instance_id}\\"
        f"Device Parameters\\Interrupt Management\\"
        f"MessageSignaledInterruptProperties"
    )
    ok1 = reg_write_tracked(winreg.HKEY_LOCAL_MACHINE, reg_path, "MSISupported", 1, 
                            change_type="msi", device_id=device_instance_id)
    ok2 = reg_write_tracked(winreg.HKEY_LOCAL_MACHINE, reg_path, "MessageNumberLimit", vector_count,
                            change_type="msi", device_id=device_instance_id)
    return {"success": ok1 and ok2, "error": None if (ok1 and ok2) else "Registry write failed"}


def disable_msi(device_instance_id, original_value=0):
    """Revert MSI mode to original value."""
    reg_path = (
        f"SYSTEM\\CurrentControlSet\\Enum\\{device_instance_id}\\"
        f"Device Parameters\\Interrupt Management\\"
        f"MessageSignaledInterruptProperties"
    )
    ok = reg_write(winreg.HKEY_LOCAL_MACHINE, reg_path, "MSISupported", original_value)
    return {"success": ok}


def set_interrupt_affinity(device_instance_id, core_mask):
    """
    Pin a device's interrupt handler to specific CPU cores.
    Uses tracked writes to ensure correct order and restoration (BUG 3).
    """
    reg_path = (
        f"SYSTEM\\CurrentControlSet\\Enum\\{device_instance_id}\\"
        f"Device Parameters\\Interrupt Management\\Affinity Policy"
    )
    
    ok1 = reg_write_tracked(winreg.HKEY_LOCAL_MACHINE, reg_path, "DevicePolicy", 4,
                            change_type="affinity", device_id=device_instance_id)
    
    mask_bytes = core_mask.to_bytes(8, byteorder='little')
    ok2 = reg_write_tracked(winreg.HKEY_LOCAL_MACHINE, reg_path,
                            "AssignmentSetOverride", mask_bytes, winreg.REG_BINARY,
                            change_type="affinity_binary", device_id=device_instance_id)
    
    return {"success": ok1 and ok2}


def remove_interrupt_affinity(device_instance_id):
    """Remove interrupt affinity pin — restore Windows default steering."""
    reg_path = (
        f"SYSTEM\\CurrentControlSet\\Enum\\{device_instance_id}\\"
        f"Device Parameters\\Interrupt Management\\Affinity Policy"
    )
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path, 0, winreg.KEY_WRITE)
        try:
            winreg.DeleteValue(key, "DevicePolicy")
            winreg.DeleteValue(key, "AssignmentSetOverride")
        except FileNotFoundError:
            pass
        winreg.CloseKey(key)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─────────────────────────────────────
# SERVICE BRIDGE (pywin32)
# ─────────────────────────────────────

def stop_service(service_name):
    """Stop a Windows service. Returns success and whether it was running."""
    try:
        status = win32serviceutil.QueryServiceStatus(service_name)
        was_running = status[1] == win32service.SERVICE_RUNNING
        if was_running:
            win32serviceutil.StopService(service_name)
        return {"success": True, "was_running": was_running}
    except Exception as e:
        logger.error(f"stop_service({service_name}): {e}")
        return {"success": False, "was_running": False, "error": str(e)}


def set_service_start_type(service_name, start_type):
    """
    Change a service start type.
    start_type: win32service.SERVICE_DISABLED (4) or SERVICE_AUTO_START (2)
    """
    try:
        scm = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_ALL_ACCESS)
        svc = win32service.OpenService(scm, service_name, win32service.SERVICE_CHANGE_CONFIG)
        win32service.ChangeServiceConfig(
            svc,
            win32service.SERVICE_NO_CHANGE,
            start_type,
            win32service.SERVICE_NO_CHANGE,
            None, None, 0, None, None, None, None
        )
        win32service.CloseServiceHandle(svc)
        win32service.CloseServiceHandle(scm)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def start_service(service_name):
    """Start a Windows service."""
    try:
        win32serviceutil.StartService(service_name)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def kill_process_by_name(exe_name):
    """Kill all running instances of a process by executable name."""
    killed = 0
    for proc in psutil.process_iter(['name', 'pid']):
        if proc.info['name'] and proc.info['name'].lower() == exe_name.lower():
            try:
                proc.kill()
                killed += 1
            except Exception:
                pass
    return {"success": True, "killed_count": killed}


def suppress_ctf():
    """
    Full CTF/TSF suppression sequence.
    Uses tracked writes to ensure registry restoration (BUG 2).
    """
    results = {}
    results['reg_input_service'] = reg_write_tracked(
        winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\Microsoft\\Input",
        "InputServiceEnabled", 0, change_type="ctf"
    )
    results['reg_input_cci'] = reg_write_tracked(
        winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\Microsoft\\Input",
        "InputServiceEnabledForCCI", 0, change_type="ctf"
    )
    results['stop_service'] = stop_service("TabletInputService")
    results['disable_service'] = set_service_start_type(
        "TabletInputService", win32service.SERVICE_DISABLED
    )
    results['kill_ctfmon'] = kill_process_by_name("ctfmon.exe")
    still_running = any(
        p.name().lower() == "ctfmon.exe" for p in psutil.process_iter(['name'])
    )
    results['verified'] = not still_running
    return results


def restore_ctf():
    """Re-enable CTF/TSF — restore registry and restart TabletInputService."""
    results = {}
    results['reg_input_service'] = reg_write(
        winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\Microsoft\\Input",
        "InputServiceEnabled", 1
    )
    results['reg_input_cci'] = reg_write(
        winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\Microsoft\\Input",
        "InputServiceEnabledForCCI", 1
    )
    results['enable_service'] = set_service_start_type(
        "TabletInputService", win32service.SERVICE_AUTO_START
    )
    results['start_service'] = start_service("TabletInputService")
    return results


# ─────────────────────────────────────
# TIMER RESOLUTION BRIDGE (ctypes)
# ─────────────────────────────────────

_ntdll = ctypes.WinDLL("ntdll.dll")

_NtSetTimerResolution = _ntdll.NtSetTimerResolution
_NtSetTimerResolution.argtypes = [
    wintypes.ULONG, wintypes.BOOL, ctypes.POINTER(wintypes.ULONG)
]
_NtSetTimerResolution.restype = wintypes.LONG

_NtQueryTimerResolution = _ntdll.NtQueryTimerResolution
_NtQueryTimerResolution.argtypes = [
    ctypes.POINTER(wintypes.ULONG),
    ctypes.POINTER(wintypes.ULONG),
    ctypes.POINTER(wintypes.ULONG)
]
_NtQueryTimerResolution.restype = wintypes.LONG


def set_timer_resolution(resolution_100ns=5000):
    """
    Set system timer resolution via undocumented NtSetTimerResolution.
    5000 = 500us (0.5ms). 10000 = 1ms. 156250 = 15.625ms (Windows default).
    """
    current = wintypes.ULONG(0)
    status = _NtSetTimerResolution(resolution_100ns, True, ctypes.byref(current))
    return {
        "success": status == 0,
        "actual_resolution_100ns": current.value,
        "actual_resolution_ms": round(current.value * 100 / 1_000_000, 4),
        "ntstatus": hex(status)
    }


def get_timer_resolution():
    """Query current, minimum (fastest), and maximum (slowest) timer resolutions."""
    min_r = wintypes.ULONG(0)
    max_r = wintypes.ULONG(0)
    cur_r = wintypes.ULONG(0)
    _NtQueryTimerResolution(ctypes.byref(min_r), ctypes.byref(max_r), ctypes.byref(cur_r))
    return {
        "current_100ns": cur_r.value,
        "current_ms": round(cur_r.value * 100 / 1_000_000, 4),
        "minimum_100ns": min_r.value,
        "maximum_100ns": max_r.value
    }


def restore_timer_resolution():
    """Restore Windows default timer resolution (15.625ms)."""
    current = wintypes.ULONG(0)
    status = _NtSetTimerResolution(156250, False, ctypes.byref(current))
    return {"success": status == 0}


# ─────────────────────────────────────
# POWERSHELL BRIDGE (subprocess)
# ─────────────────────────────────────

def run_powershell(script, timeout=30):
    """Run a PowerShell script non-interactively. Returns stdout, stderr, success."""
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive",
             "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True, text=True, timeout=timeout
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": "Command timed out", "returncode": -1}
    except Exception as e:
        return {"success": False, "stdout": "", "stderr": str(e), "returncode": -1}


def create_restore_point(description):
    """
    Create a Windows System Restore point and VERIFY it was created.
    This MUST succeed before any MSI mode or registry changes.
    Returns {success, sequence_number, error}.
    """
    script = f'''
    Enable-ComputerRestore -Drive "C:\\"
    Checkpoint-Computer -Description "{description}" -RestorePointType "MODIFY_SETTINGS"
    $points = Get-ComputerRestorePoint | Sort-Object SequenceNumber
    $latest = $points | Select-Object -Last 1
    if ($latest.Description -eq "{description}") {{
        Write-Output "SEQ:$($latest.SequenceNumber)"
    }} else {{
        Write-Output "FAILED"
    }}
    '''
    result = run_powershell(script, timeout=60)
    if result["success"] and "SEQ:" in result["stdout"]:
        seq_num = int(result["stdout"].split("SEQ:")[1].strip())
        return {"success": True, "sequence_number": seq_num, "error": None}
    return {"success": False, "sequence_number": None,
            "error": result["stderr"] or "Restore point verification failed"}


def set_cpu_isolation(cores):
    """Set bcdedit isolatedcpus. Takes effect after reboot."""
    core_str = ",".join(str(c) for c in cores)
    return run_powershell(f'bcdedit /set isolatedcpus "{core_str}"')


def remove_cpu_isolation():
    """Remove bcdedit isolatedcpus setting. Takes effect after reboot."""
    return run_powershell("bcdedit /deletevalue isolatedcpus")


def get_pci_devices():
    """
    Enumerate PCI devices with their instance IDs and friendly names.
    Uses WMI via PowerShell.
    Returns list of {device_id, friendly_name, driver_name}.
    """
    script = """
    Get-WmiObject Win32_PnPEntity | Where-Object {
        $_.PNPDeviceID -like "PCI\\*"
    } | Select-Object Name, PNPDeviceID, Service |
    ConvertTo-Json -Compress
    """
    result = run_powershell(script, timeout=15)
    if result["success"] and result["stdout"]:
        try:
            data = json.loads(result["stdout"])
            if isinstance(data, dict):
                data = [data]
            return [
                {
                    "device_id": d.get("PNPDeviceID", ""),
                    "friendly_name": d.get("Name", "Unknown"),
                    "driver_name": d.get("Service", "")
                }
                for d in data if d.get("PNPDeviceID")
            ]
        except Exception:
            pass
    return []


# ─────────────────────────────────────
# DPC MONITORING (wpr.exe + tracerpt.exe)
# ─────────────────────────────────────

def collect_dpc_data(duration_seconds=10, critical_threshold_us=500, warning_threshold_us=100):
    """
    Collect DPC data using wpr.exe + tracerpt.exe.
    Returns list of per-driver stats dicts.
    Uses column discovery for robustness (BUG 6) and threshold parameters (OPT 6).
    """
    tmp = tempfile.mkdtemp()
    etl_path = os.path.join(tmp, "dpc_trace.etl")
    csv_path = os.path.join(tmp, "dpc_trace.csv")

    try:
        # Start recording
        start_result = subprocess.run(
            ["wpr.exe", "-start", "CPU", "-filemode"],
            capture_output=True, text=True, timeout=10
        )
        if start_result.returncode != 0:
            logger.error(f"wpr start failed: {start_result.stderr}")
            return []

        time.sleep(duration_seconds)

        # Stop and save
        subprocess.run(
            ["wpr.exe", "-stop", etl_path],
            capture_output=True, text=True, timeout=30
        )

        # Convert to CSV
        subprocess.run(
            ["tracerpt.exe", etl_path, "-o", csv_path, "-of", "CSV", "-y"],
            capture_output=True, text=True, timeout=60
        )

        # Parse CSV for DPC events
        driver_data = {}
        if os.path.exists(csv_path):
            with open(csv_path, encoding='utf-8', errors='ignore') as f:
                reader = csv.DictReader(f)
                
                # Discover actual column names (BUG 6)
                fieldnames = reader.fieldnames or []
                task_col = next((c for c in fieldnames if 'task' in c.lower() or 'event' in c.lower()), None)
                provider_col = next((c for c in fieldnames if 'provider' in c.lower() or 'source' in c.lower()), None)
                duration_col = next((c for c in fieldnames if 'duration' in c.lower() or 'time' in c.lower() and 'clock' not in c.lower()), None)

                if not all([task_col, provider_col, duration_col]):
                    logger.warning(f"tracerpt CSV missing expected columns. Found: {fieldnames}. Skipping parse.")
                    return []

                for row in reader:
                    task = row.get(task_col, '')
                    if 'DPC' not in task.upper():
                        continue
                    provider = row.get(provider_col, 'unknown')
                    try:
                        duration_us = float(row.get(duration_col, 0)) / 10
                    except (ValueError, TypeError):
                        continue
                    if provider not in driver_data:
                        driver_data[provider] = []
                    driver_data[provider].append(duration_us)

        # Aggregate
        results = []
        for driver, durations in driver_data.items():
            arr = np.array(durations)
            avg = float(np.mean(arr))
            max_val = float(np.max(arr))
            std = float(np.std(arr))
            freq = len(arr)
            
            # (OPT 6)
            if max_val > critical_threshold_us or std > (critical_threshold_us * 0.4):
                severity = 'critical'
            elif max_val > warning_threshold_us or std > (warning_threshold_us * 0.5):
                severity = 'warning'
            else:
                severity = 'ok'
                
            results.append({
                "driver_name": driver,
                "avg_us": round(avg, 2),
                "max_us": round(max_val, 2),
                "std_dev_us": round(std, 2),
                "frequency": freq,
                "severity": severity
            })

        return sorted(results, key=lambda x: x["max_us"], reverse=True)

    except Exception as e:
        logger.error(f"DPC collection failed: {e}")
        return []
    finally:
        # Cleanup temp files
        for f in [etl_path, csv_path]:
            try:
                os.remove(f)
            except Exception:
                pass
        try:
            os.rmdir(tmp)
        except Exception:
            pass


# (BUG 4) Lookup Table
_HIGH_POLLING_VIDS_PIDS = {
    ("045E", "0B00"): 2000,  # Xbox Elite Series 2 via USB
    ("045E", "02FD"): 500,   # Xbox One controller via USB
    ("045E", "02E0"): 500,   # Xbox One S via USB
    ("054C", "0CE6"): 1000,  # DualSense via USB
    ("054C", "09CC"): 1000,  # DualShock 4 via USB
    ("054C", "05C4"): 500,   # DualShock 4 v1
    ("28DE", "1142"): 1000,  # Steam Controller
    ("2DC8", "6006"): 2000,  # 8BitDo Pro 2 (2000Hz mode)
    ("0F0D", "00C1"): 2000,  # HORI Fighting Commander (2000Hz)
}

_DEFAULT_POLLING_HZ = 125  # XInput default if unknown

def get_hid_controllers():
    """
    Enumerate HID game controllers via WMI.
    Detects known high-polling rate controllers (BUG 4).
    """
    script = """
    Get-WmiObject Win32_PnPEntity | Where-Object {
        $_.PNPDeviceID -like "HID\\*" -or $_.PNPDeviceID -like "USB\\VID_*"
    } | Where-Object {
        $_.Name -match "controller|gamepad|joystick|HID-compliant game"
    } | Select-Object Name, PNPDeviceID, Service, Status |
    ConvertTo-Json -Compress
    """
    result = run_powershell(script, timeout=15)
    controllers = []
    if result["success"] and result["stdout"]:
        try:
            data = json.loads(result["stdout"])
            if isinstance(data, dict):
                data = [data]
            for d in data:
                device_id = d.get("PNPDeviceID", "")
                vid = ""
                pid = ""
                if "VID_" in device_id:
                    parts = device_id.split("\\")
                    for p in parts:
                        if "VID_" in p:
                            tokens = p.split("&")
                            for t in tokens:
                                if t.startswith("VID_"):
                                    vid = t[4:8]
                                elif t.startswith("PID_"):
                                    pid = t[4:8]
                
                conn_type = "USB_WIRED"
                if "BTHLE" in device_id or "BLUETOOTH" in device_id.upper():
                    conn_type = "BLUETOOTH"
                elif "WIRELESS" in d.get("Name", "").upper():
                    conn_type = "USB_WIRELESS"

                # Polling rate detection (BUG 4)
                vid_upper = vid.upper()
                pid_upper = pid.upper()
                polling_hz = _HIGH_POLLING_VIDS_PIDS.get((vid_upper, pid_upper), _DEFAULT_POLLING_HZ)
                
                if conn_type == "BLUETOOTH":
                    polling_hz = min(polling_hz, 125)

                xinput_capped = 1 if polling_hz > 125 else 0

                if polling_hz >= 2000:
                    recommended_api = "RAW_HID"
                elif polling_hz >= 250:
                    recommended_api = "DIRECTINPUT"
                else:
                    recommended_api = "XINPUT"

                controllers.append({
                    "device_path": device_id,
                    "friendly_name": d.get("Name", "Unknown Controller"),
                    "vid": vid,
                    "pid": pid,
                    "connection_type": conn_type,
                    "polling_rate_hz": polling_hz,
                    "xinput_capped": xinput_capped,
                    "recommended_api": recommended_api
                })
        except Exception:
            pass
    return controllers
