# focus_terminal.ps1 — Bring the Hermes terminal window to foreground
# Called when user clicks a Toast notification

Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Diagnostics;

public class WindowFocus {
    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);
    
    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    
    [DllImport("user32.dll")]
    public static extern bool IsIconic(IntPtr hWnd);
    
    [DllImport("user32.dll")]
    public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
    
    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);
    
    [DllImport("user32.dll")]
    public static extern bool IsWindowVisible(IntPtr hWnd);
    
    [DllImport("user32.dll", CharSet = CharSet.Auto)]
    public static extern int GetWindowText(IntPtr hWnd, System.Text.StringBuilder lpString, int nMaxCount);
    
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
    
    static string[] terminalNames = {"windowsterminal", "wt", "powershell", "cmd", "mintty", "bash"};
    
    public static void FocusAnyTerminal() {
        EnumWindows((hWnd, lParam) => {
            if (!IsWindowVisible(hWnd)) return true;
            var sb = new System.Text.StringBuilder(256);
            GetWindowText(hWnd, sb, 256);
            string title = sb.ToString().ToLower();
            foreach (var name in terminalNames) {
                if (title.Contains(name)) {
                    if (IsIconic(hWnd)) {
                        ShowWindow(hWnd, 9); // SW_RESTORE
                    }
                    SetForegroundWindow(hWnd);
                    return false; // stop enumeration
                }
            }
            return true;
        }, IntPtr.Zero);
    }
    
    public static void FocusByPid(uint pid) {
        EnumWindows((hWnd, lParam) => {
            uint windowPid;
            GetWindowThreadProcessId(hWnd, out windowPid);
            if (windowPid == pid && IsWindowVisible(hWnd)) {
                if (IsIconic(hWnd)) {
                    ShowWindow(hWnd, 9);
                }
                SetForegroundWindow(hWnd);
                return false;
            }
            return true;
        }, IntPtr.Zero);
    }
}
"@

# Try to focus terminal by process tree first, then fallback to any terminal
try {
    # Get parent process chain: this script -> powershell -> hermes -> terminal
    $ppid = (Get-CimInstance Win32_Process -Filter "ProcessId = $PID").ParentProcessId
    $grandparent = (Get-CimInstance Win32_Process -Filter "ProcessId = $ppid").ParentProcessId
    
    # Try grandparent (likely the terminal)
    [WindowFocus]::FocusByPid([uint32]$grandparent)
    
    # If that didn't work, try parent
    Start-Sleep -Milliseconds 100
    [WindowFocus]::FocusByPid([uint32]$ppid)
} catch {
    # Fallback: find any terminal window
    [WindowFocus]::FocusAnyTerminal()
}
