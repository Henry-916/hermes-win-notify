# win_notify — Hermes Agent Windows Toast 通知插件

为 [Hermes Agent](https://github.com/NousResearch/hermes-agent) 添加 Windows 系统通知功能。

## 功能

| 通知类型 | 触发时机 | 交互方式 |
|----------|----------|----------|
| 🔔 审批通知 | 危险命令需要确认 | 4 个按钮（Once/Session/Always/Deny）直接注入审批，或点击主体跳回终端审批 |
| ✅ 完成通知 | Agent 完成回复（仅终端不在前台时） | 点击主体跳回终端 |

## 效果演示

**审批通知：**
- 点击按钮 → 直接审批，无需切回终端
- 点击通知主体 → 跳回终端 + 弹出审批提示

**完成通知：**
- Agent 完成任务后，如果你在别的窗口，会弹出通知
- 点击通知 → 跳回终端查看结果

## 安装

### 1. 安装依赖

```bash
# Hermes venv
"C:\Users\24701\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe" -m pip install winotify
```

### 2. 复制插件文件

将 `win_notify` 目录复制到 Hermes 用户插件目录：

```
C:\Users\<你的用户名>\AppData\Local\hermes\plugins\win_notify\
├── __init__.py           # 插件主逻辑
├── focus_terminal.py     # hermes:// 协议处理器
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
# 双击运行或在终端执行（只需一次，不需要管理员权限）
register_protocol.bat
```

### 4. 打 approval.py 补丁

Hermes 的审批系统没有插件接口，需要给 `tools/approval.py` 打补丁：

```bash
# 双击运行或在终端执行
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
3. → 弹出 Toast 通知（带 4 个按钮）
4. 用户点击按钮 → hermes://once/session/always/deny
5. → pythonw.exe focus_terminal.py 写入 approval_response.txt
6. → 插件读取响应 → 返回选择给审批系统
7. → 审批完成，无需切回终端
```

### 点击主体 → 跳回终端审批

```
1. 用户点击通知主体 → hermes://dismiss
2. → pythonw.exe focus_terminal.py 写入 "dismiss" + 跳转终端
3. → 插件读取 "dismiss" → 返回 None → 回退到终端审批提示
4. → 用户在终端完成审批
```

### 完成通知

```
1. Agent 输出最终回复 → transform_llm_output 钩子触发
2. → 检测终端窗口是否在前台（win32gui）
3. → 如果不在前台 → 弹出 Toast 通知
4. → 用户点击通知 → hermes://focus → 跳回终端
```

### hermes:// 自定义协议

使用 Windows 注册表注册 `hermes://` 协议处理器：
- `hermes://focus` → 跳转终端窗口
- `hermes://once` → 审批一次
- `hermes://session` → 本会话允许
- `hermes://always` → 永久允许
- `hermes://deny` → 拒绝执行
- `hermes://dismiss` → 取消通知，回退到终端审批

## 已知限制

1. **前台检测** — 使用窗口标题匹配（powershell/windowsterminal/cmd），可能不适用于所有终端
2. **超时** — 审批通知默认 60 秒超时，超时后回退到终端审批
3. **hermes update** — 需要重新运行 `patch_approval.bat` 补丁

## 依赖

- [winotify](https://github.com/versa-syahptr/winotify) — Windows Toast 通知库
- [pywin32](https://github.com/mhammond/pywin32) — Windows API 绑定（前台检测）
- Python 3.11+（Hermes venv）

## 同类项目

- [mylee04/code-notify](https://github.com/mylee04/code-notify) — Claude Code/Codex/Gemini CLI 桌面通知（功能最全）
- [DevinoSolutions/ai-agent-notifier](https://github.com/DevinoSolutions/ai-agent-notifier) — VS Code + CLI 通知
- [Hermes ntfy 集成](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/ntfy) — 官方手机推送

## 许可证

MIT License
