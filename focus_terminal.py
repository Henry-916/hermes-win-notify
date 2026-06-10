"""focus_terminal.py — Bring the Hermes terminal window to foreground.
Called via hermes:// protocol handler. Uses pythonw.exe (no window).
"""
import ctypes
import os
import sys
from pathlib import Path

user32 = ctypes.windll.user32

# Find the plugin directory and read PID file
script_dir = Path(__file__).parent
pid_file = script_dir / "hermes_pid.txt"

# Focus window by PID using EnumWindows
WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

def focus_by_pid(target_pid):
    """Find and focus the window owned by target_pid."""
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
    """Get parent process ID using ctypes + NtQueryInformationProcess."""
    import ctypes.wintypes as wintypes
    
    # Use toolhelp32 snapshot to find parent
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

def main():
    # Try to read the Hermes PID
    if pid_file.exists():
        try:
            hermes_pid = int(pid_file.read_text().strip())
        except (ValueError, OSError):
            hermes_pid = 0
        
        if hermes_pid:
            # Walk up process tree to find a window
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

if __name__ == "__main__":
    main()
