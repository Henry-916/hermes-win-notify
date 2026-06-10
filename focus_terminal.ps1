# focus_terminal.ps1 — Bring the Hermes terminal window to foreground
# Called when user clicks a Toast notification

Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Diagnostics;
using System.Text;

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
    public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);
    
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
    
    static uint _selfPid = 0;
    
    public static void FocusHermesWindow() {
        _selfPid = (uint)Process.GetCurrentProcess().Id;
        
        // First pass: look for windows with "hermes" in title
        bool found = EnumWindows((hWnd, lParam) => {
            if (!IsWindowVisible(hWnd)) return true;
            
            // Skip our own window
            uint pid;
            GetWindowThreadProcessId(hWnd, out pid);
            if (pid == _selfPid) return true;
            
            var sb = new StringBuilder(256);
            GetWindowText(hWnd, sb, 256);
            string title = sb.ToString().ToLower();
            
            if (title.Contains("hermes") || title.Contains("hermes agent")) {
                if (IsIconic(hWnd)) ShowWindow(hWnd, 9);
                SetForegroundWindow(hWnd);
                return false; // stop
            }
            return true;
        }, IntPtr.Zero);
        
        // Fallback: find any terminal window (excluding self)
        if (!found) {
            string[] names = {"windowsterminal", "powershell", "cmd", "mintty", "bash"};
            EnumWindows((hWnd, lParam) => {
                if (!IsWindowVisible(hWnd)) return true;
                uint pid;
                GetWindowThreadProcessId(hWnd, out pid);
                if (pid == _selfPid) return true;
                
                var sb = new StringBuilder(256);
                GetWindowText(hWnd, sb, 256);
                string title = sb.ToString().ToLower();
                foreach (var name in names) {
                    if (title.Contains(name)) {
                        if (IsIconic(hWnd)) ShowWindow(hWnd, 9);
                        SetForegroundWindow(hWnd);
                        return false;
                    }
                }
                return true;
            }, IntPtr.Zero);
        }
    }
}
"@

[WindowFocus]::FocusHermesWindow()
