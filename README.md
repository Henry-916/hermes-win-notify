# win_notify — Hermes Agent Windows Toast 通知插件

为 [Hermes Agent](https://github.com/NousResearch/hermes-agent) 添加 Windows 系统通知功能。

## 功能

| 通知类型 | 触发时机 | 交互方式 |
|----------|----------|----------|
| 🔔 审批通知 | 危险命令需要确认 | 4 个按钮（Once/Session/Always/Deny）直接注入审批，或点击主体跳回终端审批 |
| ✅ 完成通知 | Agent 完成回复（仅终端不在前台时） | 点击主体跳回终端 |

**通知标题显示对话名称**，例如 `[hermes通知] ✅ Hermes 任务完成`，方便区分多个 session 的通知。

## 效果演示

**审批通知：**
- 盯着终端 → 终端直接弹审批提示，不弹通知
- 不看终端 → 弹 Toast 通知，带 4 个按钮
- 点按钮 → 直接审批，不跳终端
- 点主体 → 跳回终端 + 弹终端审批提示

**完成通知：**
- Agent 完成任务后，如果你在别的窗口，会弹通知
- 点击通知 → 跳回触发通知的那个终端窗口

**多窗口支持：**
- 开多个终端窗口运行不同 session，通知精确跳转到对应的窗口
- 启动时通过进程树缓存终端窗口句柄（HWND），不依赖共享文件
- TUI 窗口重建后自动重新捕获 HWND

## 安装

### 1. 安装依赖

```bash
# 在 Hermes venv 中安装
"C:\Users\<你的用户名>\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe" -m pip install winotify pywin32
```

### 2. 复制插件文件

将 `win_notify` 目录复制到 Hermes 用户插件目录：

```
C:\Users\<你的用户名>\AppData\Local\hermes\plugins\win_notify\
├── __init__.py           # 插件主逻辑
├── focus_terminal.py     # hermes:// 协议处理器（窗口跳转 + 审批响应）
├── focus_terminal.vbs    # VBS 包装（无窗口执行）
├── focus_terminal.bat    # BAT 包装（调用 .ps1）
├── focus_terminal.ps1    # PowerShell 脚本（备用）
├── plugin.yaml           # 插件清单
├── register_protocol.bat # 注册 hermes:// 协议（运行一次）
├── patch_approval.bat    # hermes update 后重新打补丁
└── approval.patch        # approval.py 补丁文件
```

### 3. 注册 hermes:// 协议

```bash
# 双击运行（只需一次，不需要管理员权限）
register_protocol.bat
```

### 4. 打 approval.py 补丁

Hermes 的审批系统没有插件接口，需要给 `tools/approval.py` 打补丁：

```bash
# 双击运行
patch_approval.bat
```

⚠️ **每次 `hermes update` 后需要重新运行此脚本！**

### 5. 启用插件

```bash
hermes plugins enable win_notify
```

### 6. 重启 Hermes

重启会话或执行 `/reset` 让插件生效。

## 工作原理

### 审批通知流程

```
1. Hermes 检测到危险命令
2. → check_all_command_guards() → 发现 plugin_approval_handler
3. → 检测终端是否在前台
   ├── 在前台 → 返回 None，终端直接弹审批提示
   └── 不在前台 → 弹出 Toast 通知（带 4 个按钮）
4. 用户点击按钮 → hermes://once/session/always/deny
   → pythonw.exe focus_terminal.py 写入 approval_response.txt
   → 插件读取响应 → 返回选择给审批系统
   → 审批完成，无需切回终端
5. 用户点击主体 → hermes://dismiss/<hwnd>
   → pythonw.exe focus_terminal.py 写入 "dismiss" + 跳转终端
   → 插件读取 "dismiss" → 返回 None → 回退到终端审批提示
```

### 完成通知流程

```
1. Agent 输出最终回复 → transform_llm_output 钩子触发
2. → 检测终端窗口是否在前台
   ├── 在前台 → 不弹通知
   └── 不在前台 → 弹出 Toast 通知
3. 用户点击通知 → hermes://focus/<hwnd>
   → pythonw.exe focus_terminal.py 跳转到指定窗口
```

### 多窗口精确跳转

```
启动时：
  register() → _capture_terminal_hwnd()
  → 检查前台窗口是否是终端（TUI 格式: · mimo/claude/deepseek）
  → 不是则从 os.getpid() 向上遍历父进程树
  → 找到终端窗口 → 缓存到 _TERMINAL_HWND

通知创建时：
  _get_terminal_hwnd() → 返回缓存值
  → 如果缓存失效（窗口重建）→ 自动重新捕获
  → 编码到 URL: hermes://focus/<hwnd>

点击通知时：
  focus_terminal.py 解析 URL 中的 HWND
  → AttachThreadInput + BringWindowToTop 精确跳转
```

### 前台检测

```
_is_terminal_foreground() 检测策略：
  1. HWND 比较: 前台窗口 == 缓存的终端窗口（最可靠）
  2. 标题匹配: powershell/windowsterminal/cmd/mintty/bash/hermes
  3. TUI 格式: 正则 ·(mimo|claude|deepseek|gpt|gemini)
```

### hermes:// 自定义协议

| URL | 功能 |
|-----|------|
| `hermes://focus/<hwnd>` | 跳转到指定终端窗口 |
| `hermes://once` | 审批一次（不跳终端） |
| `hermes://session` | 本会话允许（不跳终端） |
| `hermes://always` | 永久允许（不跳终端） |
| `hermes://deny` | 拒绝执行（不跳终端） |
| `hermes://dismiss/<hwnd>` | 取消通知 + 跳回终端 + 弹终端审批 |

## 已知限制

1. **前台检测** — 使用 HWND 比较 + 标题匹配，在多 session 且窗口标题相同时可能误判
2. **超时** — 审批通知默认 60 秒超时，超时后回退到终端审批
3. **hermes update** — 需要重新运行 `patch_approval.bat` 补丁
4. **TUI 窗口重建** — HWND 会在窗口重建后失效，插件会自动重新捕获，但首次通知可能跳转失败

## 依赖

- [winotify](https://github.com/versa-syahptr/winotify) — Windows Toast 通知库
- [pywin32](https://github.com/mhammond/pywin32) — Windows API 绑定（前台检测、窗口跳转）
- Python 3.11+（Hermes venv）

## 同类项目

- [mylee04/code-notify](https://github.com/mylee04/code-notify) — Claude Code/Codex/Gemini CLI 桌面通知（功能最全）
- [DevinoSolutions/ai-agent-notifier](https://github.com/DevinoSolutions/ai-agent-notifier) — VS Code + CLI 通知
- [Hermes ntfy 集成](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/ntfy) — 官方手机推送

## 许可证

MIT License
