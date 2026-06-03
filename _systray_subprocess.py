"""macOS system tray icon — runs as a subprocess.

AppKit requires NSApplication.run() on the main thread.
NiceGUI (uvicorn/uvloop) already owns the main thread, so we
launch this script as a child process where the main thread
belongs to AppKit/pystray.

Usage:
    python _systray_subprocess.py <parent_pid> <port>
"""
import os
import signal
import sys
import threading
import webbrowser


def _monitor_parent(parent_pid: int) -> None:
    """Exit this process when the parent process dies."""
    import time
    while True:
        time.sleep(2)
        try:
            os.kill(parent_pid, 0)
        except (ProcessLookupError, PermissionError):
            os._exit(0)


def main() -> None:
    if len(sys.argv) < 3:
        sys.exit(1)

    parent_pid = int(sys.argv[1])
    port = int(sys.argv[2])

    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError:
        sys.exit(1)

    threading.Thread(target=_monitor_parent, args=(parent_pid,), daemon=True).start()

    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=14, fill=(59, 130, 246))
    draw.rectangle([10, 10, 34, 18], fill="white")
    draw.rectangle([18, 18, 26, 52], fill="white")
    draw.rectangle([34, 10, 42, 52], fill="white")
    draw.rectangle([34, 44, 56, 52], fill="white")

    def _on_open(icon, item):
        webbrowser.open(f"http://localhost:{port}")

    def _on_quit(icon, item):
        icon.stop()
        # Вызываем shutdown-эндпоинт — он делает nicegui_app.shutdown() + os._exit(0)
        # как UI-кнопка "Завершить". Работает независимо от режима reload и IDE.
        try:
            import urllib.request
            urllib.request.urlopen(
                f"http://127.0.0.1:{port}/_tl_ide/shutdown", timeout=3
            )
        except Exception:
            # Fallback: прямой сигнал
            try:
                os.kill(parent_pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

    menu = pystray.Menu(
        pystray.MenuItem("Открыть TL IDE", _on_open, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Завершить", _on_quit),
    )
    icon = pystray.Icon("TL IDE", img, "TL IDE", menu)
    icon.run()  # Runs on THIS process's main thread — AppKit safe


if __name__ == "__main__":
    main()
