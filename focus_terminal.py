"""focus_terminal.py — Handle hermes:// protocol actions.

Called via hermes:// protocol handler. Uses pythonw.exe (no window).
Handles:
  hermes://focus     → bring terminal to foreground
  hermes://once      → approve once + bring terminal to foreground
  hermes://session   → approve for session + bring terminal to foreground
  hermes://always    → approve permanently + bring terminal to foreground
  hermes://deny      → deny command + bring terminal to foreground
"""
import ctypes
import sys
from pathlib import Path

user32 = ctypes.windll.user32

# Paths
script_dir = Path(__file__).parent
pid_file = script_dir / "hermes_pid.txt"
response_file = script_dir / "approval_response.txt"


def focus_by_pid(target_pid):
    """Find and focus the window owned by target_pid."""
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    result = [False]

    @WNDENUMPROC
    def enum_cb(hwnd, _):
        pid = ctypes.c_uint()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == target_pid and user32.IsWindowVisible(hwnd):
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE
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


def get_parent_pid(pid):
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


def focus_terminal():
    """Focus the Hermes terminal window."""
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

    # Fallback
    focus_any_terminal()


def write_approval_response(choice: str):
    """Write the approval choice to the response file."""
    try:
        response_file.write_text(choice)
    except Exception:
        pass


def main():
    # Parse the action from command line or sys.argv
    # When launched via hermes://once, Windows passes "hermes://once" as argv[1]
    action = "focus"  # default

    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if "once" in arg:
            action = "once"
        elif "session" in arg:
            action = "session"
        elif "always" in arg:
            action = "always"
        elif "deny" in arg:
            action = "deny"
        elif "dismiss" in arg:
            action = "dismiss"
        else:
            action = "focus"

    # Handle approval actions
    if action in ("once", "session", "always", "deny"):
        write_approval_response(action)

    # Always focus the terminal
    focus_terminal()


if __name__ == "__main__":
    main()
