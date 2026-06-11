"""
Hermes Plugin: Windows Toast Notifications

Sends Windows Toast notifications when:
1. Agent needs command approval (pre_approval_request)
2. Agent finishes a turn and terminal is NOT in foreground (transform_llm_output)

Clicking any notification brings the terminal window to foreground.
Approval notifications have 4 buttons: once/session/always/deny.
Multi-window safe: passes terminal HWND via URL for precise targeting.
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

# ---------------------------------------------------------------------------
# Foreground window detection + HWND capture
# ---------------------------------------------------------------------------

try:
    import win32gui

    def _is_terminal_foreground() -> bool:
        """Check if a terminal window is currently in the foreground."""
        try:
            fg_hwnd = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(fg_hwnd).lower()
            keywords = ["powershell", "windowsterminal", "cmd", "mintty", "bash", "hermes"]
            return any(kw in title for kw in keywords)
        except Exception:
            return True

    def _get_terminal_hwnd() -> int:
        """Get the current foreground terminal window handle."""
        try:
            return win32gui.GetForegroundWindow()
        except Exception:
            return 0

except ImportError:
    logger.warning("win32gui not available — foreground detection disabled")

    def _is_terminal_foreground() -> bool:
        return False

    def _get_terminal_hwnd() -> int:
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
    fg_title = ""
    try:
        import win32gui
        fg_hwnd = win32gui.GetForegroundWindow()
        fg_title = win32gui.GetWindowText(fg_hwnd)
    except Exception:
        pass
    is_fg = _is_terminal_foreground()
    logger.info("win_notify handler: is_foreground=%s, title=[%s]", is_fg, fg_title[:60])
    if is_fg:
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
    if not _is_terminal_foreground():
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

    # Write current process PID for the focus script
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
