# focus_terminal.ps1 — Bring the Hermes terminal window to foreground
# Called when user clicks a Toast notification

Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Diagnostics;
using System.Collections.Generic;

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
    
    public static void FocusTerminalForProcess(uint targetPid) {
        // Walk up the process tree to find the terminal
        uint pid = targetPid;
        for (int i = 0; i < 10; i++) {
            try {
                Process proc = Process.GetProcessById((int)pid);
                string name = proc.ProcessName.ToLower();
                // Found a terminal process
                if (name.Contains("windowsterminal") || name.Contains("wt") || 
                    name.Contains("powershell") || name.Contains("cmd") || 
                    name.Contains("mintty") || name.Contains("bash") ||
                    name.Contains("code") || name.Contains("pycharm")) {
                    FocusWindowByPid(pid);
                    return;
                }
                // Go to parent
                pid = GetParentPid(pid);
                if (pid == 0) break;
            } catch {
                break;
            }
        }
        // Fallback: find any terminal window
        FocusAnyTerminal();
    }
    
    static uint GetParentPid(uint pid) {
        try {
            var proc = Process.GetProcessById((int)pid);
            // Use WMI to get parent PID
            var query = $"SELECT ParentProcessId FROM Win32_Process WHERE ProcessId = {pid}";
            using (var searcher = new System.Management.ManagementObjectSearcher(query)) {
                foreach (var obj in searcher.Get()) {
                    return Convert.ToUInt32(obj["ParentProcessId"]);
                }
            }
        } catch {}
        return 0;
    }
    
    public static void FocusWindowByPid(uint pid) {
        List<IntPtr> windows = new List<IntPtr>();
        EnumWindows((hWnd, lParam) => {
            uint windowPid;
            GetWindowThreadProcessId(hWnd, out windowPid);
            if (windowPid == pid && IsWindowVisible(hWnd)) {
                windows.Add(hWnd);
            }
            return true;
        }, IntPtr.Zero);
        
        foreach (var hWnd in windows) {
            if (IsIconic(hWnd)) {
                ShowWindow(hWnd, 9); // SW_RESTORE
            }
            SetForegroundWindow(hWnd);
            return;
        }
    }
    
    public static void FocusAnyTerminal() {
        string[] terminalNames = {"windowsterminal", "wt", "powershell", "cmd", "mintty"};
        EnumWindows((hWnd, lParam) => {
            if (!IsWindowVisible(hWnd)) return true;
            var sb = new System.Text.StringBuilder(256);
            GetWindowText(hWnd, sb, 256);
            string title = sb.ToString().ToLower();
            foreach (var name in terminalNames) {
                if (title.Contains(name)) {
                    if (IsIconic(hWnd)) {
                        ShowWindow(hWnd, 9);
                    }
                    SetForegroundWindow(hWnd);
                    return false; // stop enumeration
                }
            }
            return true;
        }, IntPtr.Zero);
    }
}
"@

# Get the Hermes agent PID from the script's parent process
$myPid = $PID
$parentPid = (Get-CimInstance Win32_Process -Filter "ProcessId = $myPid").ParentProcessId

# Try to focus the terminal window
[WindowFocus]::FocusTerminalForProcess([uint32]$parentPid)
