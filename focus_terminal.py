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
from pathlib import Path

user32 = ctypes.windll.user32

# Paths
script_dir = Path(__file__).parent
pid_file = script_dir / "hermes_pid.txt"
response_file = script_dir / "approval_response.txt"


def focus_by_hwnd(hwnd: int) -> bool:
    """Focus a specific window by its handle."""
    if not user32.IsWindowVisible(hwnd):
        return False
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
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
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, 9)
            user32.SetForegroundWindow(hwnd)
            result[0] = True
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
                    if user32.IsIconic(hwnd):
                        user32.ShowWindow(hwnd, 9)
                    user32.SetForegroundWindow(hwnd)
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
    # 1. Try HWND directly (most precise, multi-window safe)
    if hwnd and focus_by_hwnd(hwnd):
        return

    # 2. Try PID-based lookup
    if pid_file.exists():
        try:
            hermes_pid = int(pid_file.read_text().strip())
        except (ValueError, OSError):
            hermes_pid = 0

        if hermes_pid:
            pid = hermes_pid
            for _ in range(10):
                if focus_by_pid(pid):
                    return
                parent = get_parent_pid(pid)
                if parent == 0 or parent == pid:
                    break
                pid = parent

    # 3. Fallback: any terminal
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

    # Handle approval actions
    if action in ("once", "session", "always", "deny"):
        write_approval_response(action)
        focus_terminal(hwnd)
    elif action == "dismiss":
        write_approval_response("dismiss")
        focus_terminal(hwnd)
    else:
        # Default: just focus
        focus_terminal(hwnd)


def main():
    if len(sys.argv) > 1:
        url = sys.argv[1]
        parse_url_and_act(url)
    else:
        focus_terminal()


if __name__ == "__main__":
    main()
