# focus_terminal.ps1 — Bring the Hermes terminal window to foreground
# Reads hermes_pid.txt to find the Hermes agent process, then walks up
# the process tree to find and focus the terminal window.

$ErrorActionPreference = 'SilentlyContinue'

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
    
    public static bool FocusWindowByPid(uint targetPid) {
        bool found = false;
        EnumWindows((hWnd, lParam) => {
            if (!IsWindowVisible(hWnd)) return true;
            uint pid;
            GetWindowThreadProcessId(hWnd, out pid);
            if (pid == targetPid) {
                if (IsIconic(hWnd)) ShowWindow(hWnd, 9);
                SetForegroundWindow(hWnd);
                found = true;
                return false;
            }
            return true;
        }, IntPtr.Zero);
        return found;
    }
    
    public static void FocusAnyTerminal() {
        string[] names = {"windowsterminal", "powershell", "cmd", "mintty", "bash"};
        EnumWindows((hWnd, lParam) => {
            if (!IsWindowVisible(hWnd)) return true;
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
"@

# Read the PID file
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pidFile = Join-Path $scriptDir "hermes_pid.txt"

if (Test-Path $pidFile) {
    $hermesPid = [int](Get-Content $pidFile -Raw).Trim()
    
    # Walk up the process tree from the Hermes PID to find the terminal
    $pid = $hermesPid
    $focused = $false
    for ($i = 0; $i -lt 10; $i++) {
        $proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
        if (-not $proc) { break }
        
        # Check if this process has a visible window
        if ($proc.MainWindowHandle -ne 0) {
            [WindowFocus]::FocusWindowByPid([uint32]$pid)
            $focused = $true
            break
        }
        
        # Go to parent process
        $cim = Get-CimInstance Win32_Process -Filter "ProcessId = $pid" -ErrorAction SilentlyContinue
        if (-not $cim -or -not $cim.ParentProcessId) { break }
        $pid = $cim.ParentProcessId
    }
    
    if (-not $focused) {
        [WindowFocus]::FocusAnyTerminal()
    }
} else {
    # No PID file, fallback to any terminal
    [WindowFocus]::FocusAnyTerminal()
}
