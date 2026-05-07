"""
MeasureSleep — measures actual achieved timer resolution.
Based on the methodology of Mark Russinovich's MeasureSleep tool.
Complements NtQueryTimerResolution by showing what the system ACTUALLY achieves
vs what it reports.
"""

import time
import statistics
import ctypes
from ctypes import wintypes

# Load NtQueryTimerResolution for comparison
_ntdll = ctypes.WinDLL("ntdll.dll")
_NtQueryTimerResolution = _ntdll.NtQueryTimerResolution
_NtQueryTimerResolution.argtypes = [
    ctypes.POINTER(wintypes.ULONG),
    ctypes.POINTER(wintypes.ULONG),
    ctypes.POINTER(wintypes.ULONG)
]
_NtQueryTimerResolution.restype = wintypes.LONG


def get_reported_resolution() -> dict:
    """Get what NtQueryTimerResolution reports."""
    min_r = wintypes.ULONG(0)
    max_r = wintypes.ULONG(0)
    cur_r = wintypes.ULONG(0)
    _NtQueryTimerResolution(
        ctypes.byref(min_r),
        ctypes.byref(max_r),
        ctypes.byref(cur_r)
    )
    return {
        "current_100ns": cur_r.value,
        "current_ms": round(cur_r.value * 100 / 1_000_000, 4),
        "minimum_100ns": min_r.value,
        "minimum_ms": round(min_r.value * 100 / 1_000_000, 4),
        "maximum_100ns": max_r.value,
        "maximum_ms": round(max_r.value * 100 / 1_000_000, 4),
    }


def measure_actual_resolution(
    target_sleep_ms: float = 1.0,
    iterations: int = 100,
    progress_callback=None
) -> dict:
    """
    Measure actual achieved timer resolution by testing sleep precision.

    Args:
        target_sleep_ms: The sleep duration to test in milliseconds (default 1.0ms)
        iterations: Number of test iterations (default 100 for statistical reliability)
        progress_callback: Optional callable(current, total) for UI progress updates

    Returns:
        dict with avg_ms, min_ms, max_ms, std_dev_ms, overshoot_ms,
        reported_ms, accuracy_percent, grade
    """
    target_seconds = target_sleep_ms / 1000.0
    overshoots = []

    for i in range(iterations):
        start = time.perf_counter()
        time.sleep(target_seconds)
        end = time.perf_counter()

        actual_ms = (end - start) * 1000.0
        overshoot_ms = actual_ms - target_sleep_ms
        overshoots.append(overshoot_ms)

        if progress_callback:
            progress_callback(i + 1, iterations)

    avg_overshoot = statistics.mean(overshoots)
    min_overshoot = min(overshoots)
    max_overshoot = max(overshoots)
    std_dev = statistics.stdev(overshoots) if len(overshoots) > 1 else 0.0

    # The effective timer resolution = average overshoot + target
    effective_resolution_ms = target_sleep_ms + avg_overshoot

    # Get reported resolution for comparison
    reported = get_reported_resolution()
    reported_ms = reported["current_ms"]

    # Accuracy: how close is actual to what was requested
    # 100% = perfect, lower = worse
    if effective_resolution_ms > 0:
        accuracy = (target_sleep_ms / effective_resolution_ms) * 100
        accuracy = min(accuracy, 100.0)
    else:
        accuracy = 100.0

    # Grade the result
    if avg_overshoot < 0.1:
        grade = "EXCELLENT"
        grade_color = "success"
    elif avg_overshoot < 0.5:
        grade = "GOOD"
        grade_color = "success"
    elif avg_overshoot < 1.0:
        grade = "ACCEPTABLE"
        grade_color = "warning"
    elif avg_overshoot < 2.0:
        grade = "POOR"
        grade_color = "warning"
    else:
        grade = "CRITICAL"
        grade_color = "danger"

    return {
        "target_ms": target_sleep_ms,
        "iterations": iterations,
        "avg_overshoot_ms": round(avg_overshoot, 4),
        "min_overshoot_ms": round(min_overshoot, 4),
        "max_overshoot_ms": round(max_overshoot, 4),
        "std_dev_ms": round(std_dev, 4),
        "effective_resolution_ms": round(effective_resolution_ms, 4),
        "reported_resolution_ms": reported_ms,
        "accuracy_percent": round(accuracy, 1),
        "grade": grade,
        "grade_color": grade_color,
        "delta_from_reported_ms": round(effective_resolution_ms - reported_ms, 4),
        "raw_overshoots": overshoots  # full dataset for graphing
    }


def run_full_benchmark(progress_callback=None) -> dict:
    """
    Run a complete sleep precision benchmark at multiple target durations.
    Tests 0.5ms, 1.0ms, 2.0ms to show how resolution holds across the range.
    """
    results = {}
    targets = [0.5, 1.0, 2.0]
    total_iterations = len(targets) * 100

    completed = 0

    def sub_progress(current, total):
        nonlocal completed
        completed += 1
        if progress_callback:
            progress_callback(completed, total_iterations)

    for t in targets:
        results[f"{t}ms"] = measure_actual_resolution(
            target_sleep_ms=t,
            iterations=100,
            progress_callback=sub_progress
        )

    return results