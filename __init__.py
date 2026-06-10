"""
Hermes Plugin: Windows Toast Notifications

Sends Windows Toast notifications when:
1. Agent needs command approval (pre_approval_request)
2. A tool call fails (post_tool_call with error)
3. Agent finishes a turn and terminal is NOT in foreground (transform_llm_output)
"""

import logging
import threading
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Foreground window detection
# ---------------------------------------------------------------------------

_TERMINAL_KEYWORDS = [
    "windowsterminal",
    "powershell",
    "cmd",
    "mintty",
    "git-bash",
    "visual studio code",  # VS Code integrated terminal
    "hermes",
    "pycharm",
    "intellij",
]

try:
    import win32gui

    def _is_terminal_foreground() -> bool:
        """Check if a terminal window is currently in the foreground."""
        try:
            hwnd = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(hwnd).lower()
            return any(kw in title for kw in _TERMINAL_KEYWORDS)
        except Exception:
            # If detection fails, assume terminal IS foreground (don't notify)
            return True

except ImportError:
    logger.warning("win32gui not available — foreground detection disabled, notifications will always show")

    def _is_terminal_foreground() -> bool:
        return False


# ---------------------------------------------------------------------------
# Toast notification helper
# ---------------------------------------------------------------------------

try:
    from winotify import Notification, audio

    def _show_toast(title: str, body: str, msg_type: str = "info") -> None:
        """Show a Windows Toast notification in a background thread."""
        def _fire():
            try:
                toast = Notification(
                    app_id="Hermes Agent",
                    title=title,
                    msg=body,
                    duration="long",
                )
                # Set audio based on notification type
                if msg_type == "approval":
                    toast.set_audio(audio.LoopingAlarm, loop=False)
                elif msg_type == "error":
                    toast.set_audio(audio.LoopingAlarm2, loop=False)
                else:
                    toast.set_audio(audio.Default, loop=False)
                toast.show()
            except Exception as e:
                logger.error("Failed to show toast: %s", e)

        # Fire in background thread to avoid blocking the agent
        threading.Thread(target=_fire, daemon=True).start()

except ImportError:
    logger.error("winotify not installed — notifications disabled")

    def _show_toast(title: str, body: str, msg_type: str = "info") -> None:
        pass


# ---------------------------------------------------------------------------
# Hook callbacks
# ---------------------------------------------------------------------------

def _on_pre_approval_request(**kwargs: Any) -> None:
    """Fired when a dangerous command needs user approval."""
    command = kwargs.get("command", "")
    description = kwargs.get("description", "")
    body = command[:200] if command else description[:200]
    print(f"[win_notify] PRE_APPROVAL hook fired! command={command[:50]}")  # DEBUG
    _show_toast(
        title="\U0001f514 Hermes \u9700\u8981\u5ba1\u6279",
        body=body,
        msg_type="approval",
    )


def _on_post_tool_call(**kwargs: Any) -> None:
    """Fired after a tool call. Notify only on errors."""
    status = kwargs.get("status", "")
    if status != "error":
        return

    tool_name = kwargs.get("tool_name", "unknown")
    error_msg = kwargs.get("error_message", "") or kwargs.get("result", "")
    # Truncate long error messages
    body = f"{tool_name}: {str(error_msg)[:150]}" if error_msg else tool_name

    _show_toast(
        title="\u274c Hermes \u9047\u5230\u9519\u8bef",
        body=body,
        msg_type="error",
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
    return None  # Don't transform the output


# ---------------------------------------------------------------------------
# Plugin entry point
# ---------------------------------------------------------------------------

def register(ctx: Any) -> None:
    """Register notification hooks with Hermes."""
    ctx.register_hook("pre_approval_request", _on_pre_approval_request)
    ctx.register_hook("post_tool_call", _on_post_tool_call)
    ctx.register_hook("transform_llm_output", _on_transform_llm_output)
    logger.info("win_notify plugin registered: approval + error + completion notifications")
