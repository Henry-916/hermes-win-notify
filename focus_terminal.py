"""focus_terminal.py — Handle hermes:// protocol actions.

Called via hermes:// protocol handler. Uses pythonw.exe (no window).
Handles:
  hermes://focus[/hwnd]     → bring terminal to foreground (optionally by HWND)
  hermes://once             → approve once
  hermes://session          → approve for session
  hermes://always           → approve permanently
  hermes://deny             → deny command
  hermes://dismiss[/hwnd]   → dismiss notification, show terminal approval
"""
import ctypes
import sys
import time
from pathlib import Path

user32 = ctypes.windll.user32

# Paths
script_dir = Path(__file__).parent
pid_file = script_dir / "hermes_pid.txt"
response_file = script_dir / "approval_response.txt"
log_file = script_dir / "focus_debug.log"


def log(msg: str):
    """Append debug message to log file."""
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"{msg}\n")
    except Exception:
        pass


def focus_by_hwnd(hwnd: int) -> bool:
    """Focus a specific window by its handle.

    Uses AttachThreadInput + BringWindowToTop for reliable focus switching.
    Windows restricts SetForegroundWindow from background processes, so we
    attach to the foreground thread's input queue first.
    """
    if not hwnd or not user32.IsWindow(hwnd):
        log(f"focus_by_hwnd: invalid hwnd={hwnd}")
        return False
    if not user32.IsWindowVisible(hwnd):
        log(f"focus_by_hwnd: hwnd={hwnd} not visible")
        return False

    title_buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, title_buf, 256)
    log(f"focus_by_hwnd: targeting hwnd={hwnd}, title=[{title_buf.value[:50]}]")

    # Get current foreground thread
    fg_hwnd = user32.GetForegroundWindow()
    fg_thread = user32.GetWindowThreadProcessId(fg_hwnd, None)
    target_thread = user32.GetWindowThreadProcessId(hwnd, None)
    log(f"  fg_hwnd={fg_hwnd}, fg_thread={fg_thread}, target_thread={target_thread}")

    # Attach to foreground thread input (required for SetForegroundWindow to work)
    attach_result = user32.AttachThreadInput(target_thread, fg_thread, True)
    log(f"  AttachThreadInput result={attach_result}")

    # Bring window to top
    user32.BringWindowToTop(hwnd)

    # Restore if minimized
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE

    # Set foreground
    sf_result = user32.SetForegroundWindow(hwnd)
    log(f"  SetForegroundWindow result={sf_result}")

    # Detach thread input
    user32.AttachThreadInput(target_thread, fg_thread, False)

    # Verify
    time.sleep(0.2)
    new_fg = user32.GetForegroundWindow()
    new_fg_title = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(new_fg, new_fg_title, 256)
    log(f"  Verify: new_fg={new_fg}, title=[{new_fg_title.value[:50]}]")

    return True


def focus_by_pid(target_pid: int) -> bool:
    """Find and focus the window owned by target_pid."""
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    result = [False]

    @WNDENUMPROC
    def enum_cb(hwnd, _):
        pid = ctypes.c_uint()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == target_pid and user32.IsWindowVisible(hwnd):
            result[0] = focus_by_hwnd(hwnd)
            return False  # stop
        return True

    user32.EnumWindows(enum_cb, 0)
    return result[0]


def focus_any_terminal():
    """Fallback: find any terminal window."""
    names = [b"powershell", b"cmd", b"windowsterminal", b"mintty", b"bash"]
    buf = ctypes.create_unicode_buffer(256)

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    @WNDENUMPROC
    def enum_cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextW(hwnd, buf, 256)
        if length > 0:
            title = buf.value.lower().encode("utf-8")
            for name in names:
                if name in title:
                    if focus_by_hwnd(hwnd):
                        return False
        return True

    user32.EnumWindows(enum_cb, 0)


def get_parent_pid(pid: int) -> int:
    """Get parent process ID using CreateToolhelp32Snapshot."""
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


def focus_terminal(hwnd: int = 0):
    """Focus the Hermes terminal window.

    If hwnd is provided and valid, use it directly (most precise).
    Otherwise fall back to PID-based lookup, then to any terminal.
    """
    log(f"focus_terminal called with hwnd={hwnd}")

    # 1. Try HWND directly (most precise, multi-window safe)
    if hwnd and focus_by_hwnd(hwnd):
        log("focus_terminal: HWND focus succeeded")
        return

    # 2. Try PID-based lookup
    if pid_file.exists():
        try:
            hermes_pid = int(pid_file.read_text().strip())
            log(f"focus_terminal: trying PID={hermes_pid}")
        except (ValueError, OSError):
            hermes_pid = 0

        if hermes_pid:
            pid = hermes_pid
            for _ in range(10):
                if focus_by_pid(pid):
                    log("focus_terminal: PID focus succeeded")
                    return
                parent = get_parent_pid(pid)
                if parent == 0 or parent == pid:
                    break
                pid = parent

    # 3. Fallback: any terminal
    log("focus_terminal: falling back to any terminal")
    focus_any_terminal()


def write_approval_response(choice: str):
    """Write the approval choice to the response file."""
    try:
        response_file.write_text(choice)
    except Exception:
        pass


def parse_url_and_act(url: str):
    """Parse hermes:// URL and perform the appropriate action.

    Supported URLs:
      hermes://focus           → focus terminal (PID fallback)
      hermes://focus/12345     → focus specific window by HWND
      hermes://once            → approve once
      hermes://session         → approve for session
      hermes://always          → approve permanently
      hermes://deny            → deny command
      hermes://dismiss         → dismiss, show terminal approval
      hermes://dismiss/12345   → dismiss, focus specific window + show approval
    """
    log(f"parse_url_and_act: url=[{url}]")
    url_lower = url.lower()
    hwnd = 0

    # Extract action and optional HWND
    # Format: hermes://action[/hwnd]
    parts = url_lower.replace("hermes://", "").split("/")
    action = parts[0] if parts else "focus"

    # Try to extract HWND from URL
    if len(parts) > 1:
        try:
            hwnd = int(parts[1])
        except ValueError:
            hwnd = 0

    log(f"  action={action}, hwnd={hwnd}")

    # Handle approval actions — write response, no terminal jump
    if action in ("once", "session", "always", "deny"):
        write_approval_response(action)
        return  # Don't focus terminal — let Hermes handle it

    # Dismiss — write response AND focus terminal
    if action == "dismiss":
        write_approval_response("dismiss")
        focus_terminal(hwnd)
        return

    # Default: just focus
    focus_terminal(hwnd)


def main():
    log(f"--- focus_terminal.py started, argv={sys.argv} ---")
    if len(sys.argv) > 1:
        url = sys.argv[1]
        parse_url_and_act(url)
    else:
        focus_terminal()
    log("--- focus_terminal.py done ---")


if __name__ == "__main__":
    main()
