"""
Hermes Plugin: Windows Toast Notifications

Sends Windows Toast notifications when:
1. Agent needs command approval (pre_approval_request)
2. Agent finishes a turn and terminal is NOT in foreground (transform_llm_output)

Clicking any notification brings the terminal window to foreground.
Approval notifications have 4 buttons: once/session/always/deny.
Multi-window safe: captures terminal HWND once at startup via process tree walk.
"""

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Paths
_SCRIPT_DIR = Path(__file__).parent
_PID_FILE = _SCRIPT_DIR / "hermes_pid.txt"
_APPROVAL_REQUEST_FILE = _SCRIPT_DIR / "approval_request.txt"
_APPROVAL_RESPONSE_FILE = _SCRIPT_DIR / "approval_response.txt"

# Cached terminal HWND — captured once at register() time, multi-session safe.
# 0 means "not yet captured" or "capture failed".
_TERMINAL_HWND: int = 0

# ---------------------------------------------------------------------------
# Foreground window detection + HWND capture
# ---------------------------------------------------------------------------

try:
    import win32gui
    import ctypes

    def _is_terminal_foreground() -> bool:
        """Check if a terminal window is currently in the foreground.

        Uses the cached _TERMINAL_HWND for reliable detection in TUI mode.
        Falls back to title-based detection if HWND is not available.
        """
        try:
            # Validate cached HWND is still alive
            global _TERMINAL_HWND
            if _TERMINAL_HWND and not win32gui.IsWindow(_TERMINAL_HWND):
                _TERMINAL_HWND = 0  # Window destroyed, invalidate cache

            fg_hwnd = win32gui.GetForegroundWindow()

            # Fast: compare foreground HWND with cached terminal HWND
            if _TERMINAL_HWND and fg_hwnd == _TERMINAL_HWND:
                return True

            # Fallback: title-based detection (less reliable in multi-session)
            title = win32gui.GetWindowText(fg_hwnd).lower()
            keywords = ["powershell", "windowsterminal", "cmd", "mintty", "bash", "hermes"]
            return any(kw in title for kw in keywords)
        except Exception:
            return False  # On error, assume NOT foreground → show notification

    def _get_terminal_hwnd() -> int:
        """Return the cached terminal HWND captured at register() time.

        Multi-session safe: each Hermes process captures its own HWND once
        at startup, avoiding the shared hermes_pid.txt race condition.
        """
        return _TERMINAL_HWND

    def _capture_terminal_hwnd() -> int:
        """Capture the terminal HWND for THIS Hermes session.

        Called once at register() time when the terminal is likely foreground.
        Strategy (multi-session safe — uses only os.getpid(), never shared files):
        1. Fast path: if foreground window is a terminal, use it
        2. Walk parent process tree from os.getpid(), find first visible window
        3. Fallback: any window with 'hermes' in title
        """
        try:
            # 1. Fast path: terminal in foreground (typical at startup)
            fg_hwnd = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(fg_hwnd).lower()
            keywords = ["powershell", "windowsterminal", "cmd", "mintty", "bash", "hermes"]
            if any(kw in title for kw in keywords):
                return fg_hwnd

            # 2. Walk parent process tree to find terminal window
            result = _find_hwnd_by_process_tree(os.getpid())
            if result:
                return result

            # 3. Fallback: any window with 'hermes' in title
            return _find_hermes_window()
        except Exception:
            return 0

    def _find_hwnd_by_process_tree(start_pid: int) -> int:
        """Walk the parent process chain from start_pid and return the HWND
        of the first visible window found.

        In CLI mode, the Hermes Python process doesn't own visible windows;
        we walk up to the shell → terminal emulator to find the terminal HWND.
        """
        pid = start_pid
        for _ in range(10):
            result = _find_hwnd_by_pid(pid)
            if result:
                return result
            parent = _get_parent_pid(pid)
            if parent == 0 or parent == pid:
                break
            pid = parent
        return 0

    def _get_parent_pid(pid: int) -> int:
        """Get the parent process ID using CreateToolhelp32Snapshot."""
        TH32CS_SNAPPROCESS = 0x00000002

        class PROCESSENTRY32(ctypes.Structure):
            _fields_ = [
                ("dwSize", ctypes.c_uint),
                ("cntUsage", ctypes.c_uint),
                ("th32ProcessID", ctypes.c_uint),
                ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
                ("th32ModuleID", ctypes.c_uint),
                ("cntThreads", ctypes.c_uint),
                ("th32ParentProcessID", ctypes.c_uint),
                ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", ctypes.c_uint),
                ("szExeFile", ctypes.c_char * 260),
            ]

        kernel32 = ctypes.windll.kernel32
        snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if snapshot == -1:
            return 0

        entry = PROCESSENTRY32()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32)

        parent = 0
        if kernel32.Process32First(snapshot, ctypes.byref(entry)):
            while True:
                if entry.th32ProcessID == pid:
                    parent = entry.th32ParentProcessID
                    break
                if not kernel32.Process32Next(snapshot, ctypes.byref(entry)):
                    break

        kernel32.CloseHandle(snapshot)
        return parent

    def _find_hwnd_by_pid(target_pid: int) -> int:
        """Find the visible window owned by target_pid."""
        result = [0]

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def enum_cb(hwnd, _):
            pid = ctypes.c_uint()
            win32gui.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == target_pid and win32gui.IsWindowVisible(hwnd):
                result[0] = hwnd
                return False  # stop
            return True

        win32gui.EnumWindows(enum_cb, 0)
        return result[0]

    def _find_hermes_window() -> int:
        """Find any visible window with 'hermes' in the title."""
        result = [0]
        buf = ctypes.create_unicode_buffer(256)

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def enum_cb(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd):
                return True
            length = win32gui.GetWindowTextW(hwnd, buf, 256)
            if length > 0 and "hermes" in buf.value.lower():
                result[0] = hwnd
                return False  # stop
            return True

        win32gui.EnumWindows(enum_cb, 0)
        return result[0]

except ImportError:
    logger.warning("win32gui not available — foreground detection disabled")

    def _is_terminal_foreground() -> bool:
        return False

    def _get_terminal_hwnd() -> int:
        return 0

    def _capture_terminal_hwnd() -> int:
        return 0


def _focus_url(hwnd: int = 0) -> str:
    """Build a hermes://focus URL with optional HWND for precise targeting."""
    if hwnd:
        return f"hermes://focus/{hwnd}"
    return "hermes://focus"


# ---------------------------------------------------------------------------
# Toast notification helper
# ---------------------------------------------------------------------------

try:
    from winotify import Notification

    def _show_toast(title: str, body: str, msg_type: str = "info") -> None:
        """Show a Windows Toast notification in a background thread."""
        hwnd = _get_terminal_hwnd()

        def _fire():
            try:
                toast = Notification(
                    app_id="Hermes Agent",
                    title=title,
                    msg=body,
                    duration="long",
                    launch=_focus_url(hwnd),
                )
                toast.show()
            except Exception as e:
                logger.error("Failed to show toast: %s", e)

        threading.Thread(target=_fire, daemon=True).start()

    def _show_approval_toast(command: str, description: str) -> None:
        """Show approval Toast with 4 action buttons."""
        hwnd = _get_terminal_hwnd()

        def _fire():
            try:
                body = command[:200] if command else description[:200]
                toast = Notification(
                    app_id="Hermes Agent",
                    title="\U0001f514 Hermes \u9700\u8981\u5ba1\u6279",
                    msg=body,
                    duration="long",
                    launch=f"hermes://dismiss/{hwnd}",
                )
                toast.add_actions("Once", "hermes://once")
                toast.add_actions("Session", "hermes://session")
                toast.add_actions("Always", "hermes://always")
                toast.add_actions("Deny", "hermes://deny")
                toast.show()
            except Exception as e:
                logger.error("Failed to show approval toast: %s", e)

        threading.Thread(target=_fire, daemon=True).start()

except ImportError:
    logger.error("winotify not installed — notifications disabled")

    def _show_toast(title: str, body: str, msg_type: str = "info") -> None:
        pass

    def _show_approval_toast(command: str, description: str) -> None:
        pass


# ---------------------------------------------------------------------------
# Plugin approval handler
# ---------------------------------------------------------------------------

def _plugin_approval_handler(command: str, description: str, timeout: int) -> Optional[str]:
    """Called by the approval system when a dangerous command needs approval.

    Shows a Toast with 4 buttons and waits for the user's choice.
    Returns 'once', 'session', 'always', 'deny', or None (timeout/no response).
    """
    # If terminal is in foreground, skip toast and let terminal handle it
    if _is_terminal_foreground():
        return None

    # Clean up any stale response file
    try:
        _APPROVAL_RESPONSE_FILE.unlink(missing_ok=True)
    except Exception:
        pass

    # Write the approval request (for the protocol handler to read)
    try:
        _APPROVAL_REQUEST_FILE.write_text(f"{command}\n{description}")
    except Exception:
        pass

    # Show the Toast with buttons
    _show_approval_toast(command, description)

    # Wait for the response file to appear
    start = time.time()
    while time.time() - start < timeout:
        try:
            if _APPROVAL_RESPONSE_FILE.exists():
                choice = _APPROVAL_RESPONSE_FILE.read_text().strip()
                if choice in ("once", "session", "always", "deny", "dismiss"):
                    # Clean up
                    try:
                        _APPROVAL_RESPONSE_FILE.unlink(missing_ok=True)
                        _APPROVAL_REQUEST_FILE.unlink(missing_ok=True)
                    except Exception:
                        pass
                    # "dismiss" means user wants terminal prompt
                    if choice == "dismiss":
                        return None
                    return choice
        except Exception:
            pass
        time.sleep(0.5)

    # Timeout — clean up and return None (fall through to CLI)
    try:
        _APPROVAL_REQUEST_FILE.unlink(missing_ok=True)
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Hook callbacks
# ---------------------------------------------------------------------------

def _on_pre_approval_request(**kwargs: Any) -> None:
    """Fired when a dangerous command needs user approval."""
    # Don't show the simple notification if plugin approval handler is active
    from tools.approval import _plugin_approval_handler as handler
    if handler is not None:
        return

    command = kwargs.get("command", "")
    description = kwargs.get("description", "")
    body = command[:200] if command else description[:200]
    _show_toast(
        title="\U0001f514 Hermes \u9700\u8981\u5ba1\u6279",
        body=body,
        msg_type="approval",
    )


def _on_transform_llm_output(**kwargs: Any) -> Optional[str]:
    """Fired when LLM produces final text output (= turn ends).

    Only sends notification if terminal is NOT in foreground.
    Returns None (no transformation to the output).
    """
    is_fg = _is_terminal_foreground()
    fg_hwnd = 0
    try:
        fg_hwnd = win32gui.GetForegroundWindow()
    except Exception:
        pass
    logger.info("win_notify completion: is_fg=%s, fg_hwnd=%s, cached_hwnd=%s", is_fg, fg_hwnd, _TERMINAL_HWND)
    if not is_fg:
        logger.info("win_notify: terminal NOT in foreground, showing completion notification")
        _show_toast(
            title="\u2705 Hermes \u4efb\u52a1\u5b8c\u6210",
            body="\u56de\u5230\u7ec8\u7aef\u67e5\u770b\u7ed3\u679c",
            msg_type="complete",
        )
    return None


# ---------------------------------------------------------------------------
# Plugin entry point
# ---------------------------------------------------------------------------

def register(ctx: Any) -> None:
    """Register notification hooks with Hermes."""
    ctx.register_hook("pre_approval_request", _on_pre_approval_request)
    ctx.register_hook("transform_llm_output", _on_transform_llm_output)
    logger.info("win_notify plugin registered: approval + completion notifications")

    # Capture terminal HWND for THIS session (before PID file — which is
    # still written for backward compatibility with focus_terminal.py fallback)
    global _TERMINAL_HWND
    _TERMINAL_HWND = _capture_terminal_hwnd()
    logger.info("win_notify: captured terminal HWND = %d", _TERMINAL_HWND)

    # Write current process PID for the focus script (backward compat)
    try:
        _PID_FILE.write_text(str(os.getpid()))
        logger.info("win_notify: wrote PID %d to %s", os.getpid(), _PID_FILE)
    except Exception as e:
        logger.warning("win_notify: failed to write PID file: %s", e)

    # Register the plugin approval handler
    try:
        from tools.approval import set_plugin_approval_handler
        set_plugin_approval_handler(_plugin_approval_handler)
        logger.info("win_notify: registered plugin approval handler (Toast with buttons)")
    except Exception as e:
        logger.warning("win_notify: failed to register approval handler: %s", e)
