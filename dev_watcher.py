# dev_watcher.py
"""
OP TOOL Auto-Build Watcher
Run this during development: python dev_watcher.py
It watches all .py files and rebuilds the EXE on any change.
Do NOT include this file in the PyInstaller build.
"""

import subprocess
import time
import sys
import os
from pathlib import Path

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except ImportError:
    print("Installing watchdog...")
    subprocess.run([sys.executable, "-m", "pip", "install", "watchdog"], check=True)
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler


class RebuildHandler(FileSystemEventHandler):
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self._last_build = 0
        self._build_cooldown = 3.0  # seconds — prevent double-triggers on rapid saves
        self._building = False

    def on_modified(self, event):
        if event.is_directory:
            return

        path = Path(event.src_path)

        # Only trigger on Python source files
        if path.suffix != ".py":
            return

        # Ignore PyInstaller internals and pycache
        parts = path.parts
        if any(p in ("build", "dist", "__pycache__") for p in parts):
            return

        # Ignore the watcher itself
        if path.name == "dev_watcher.py":
            return

        now = time.time()
        if self._building or (now - self._last_build) < self._build_cooldown:
            return

        self._last_build = now
        print(f"\n[WATCHER] Change detected: {path.name}")
        self._trigger_build()

    def _trigger_build(self):
        self._building = True
        start = time.time()
        print("[WATCHER] Starting PyInstaller rebuild...")
        print("[WATCHER] " + "─" * 50)

        spec_path = self.project_root / "optool.spec"
        result = subprocess.run(
            [sys.executable, "-m", "PyInstaller", str(spec_path), "--noconfirm"],
            cwd=str(self.project_root),
            capture_output=False  # show output live
        )

        elapsed = time.time() - start
        print("[WATCHER] " + "─" * 50)

        if result.returncode == 0:
            exe_path = self.project_root / "dist" / "OPTOOL" / "OPTOOL.exe"
            size_mb = exe_path.stat().st_size / (1024 * 1024) if exe_path.exists() else 0
            print(f"[WATCHER] ✓ Build complete in {elapsed:.1f}s — EXE: {size_mb:.1f}MB")
            print(f"[WATCHER] → {exe_path}")
        else:
            print(f"[WATCHER] ✗ Build FAILED in {elapsed:.1f}s (exit code {result.returncode})")

        self._building = False


def main():
    project_root = Path(__file__).parent.resolve()
    print(f"[WATCHER] OP TOOL Auto-Build Watcher")
    print(f"[WATCHER] Watching: {project_root}")
    print(f"[WATCHER] Any .py file change triggers: pyinstaller optool.spec --noconfirm")
    print(f"[WATCHER] Press Ctrl+C to stop")
    print("[WATCHER] " + "─" * 50)

    handler = RebuildHandler(project_root)
    observer = Observer()
    observer.schedule(handler, str(project_root), recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[WATCHER] Stopping...")
        observer.stop()

    observer.join()
    print("[WATCHER] Stopped.")


if __name__ == "__main__":
    main()