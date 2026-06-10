@echo off
REM patch_approval.bat — Re-apply win_notify approval patch after hermes update
REM Run this after every `hermes update` to restore the plugin approval channel

echo Applying win_notify approval patch to tools/approval.py...

python -c "
import sys
target = r'C:\Users\24701\AppData\Local\hermes\hermes-agent\tools\approval.py'
patch_file = r'C:\Users\24701\AppData\Local\hermes\plugins\win_notify\approval.patch'

# Check if patch already applied
with open(target, 'r', encoding='utf-8') as f:
    content = f.read()

if 'set_plugin_approval_handler' in content:
    print('Patch already applied, skipping.')
    sys.exit(0)

# Read patch file
with open(patch_file, 'r', encoding='utf-8') as f:
    patch = f.read()

# Extract the added lines (lines starting with '+')
added_lines = []
for line in patch.split('\n'):
    if line.startswith('+') and not line.startswith('+++'):
        added_lines.append(line[1:])

# Find insertion points
# 1. Add set/clear functions after _gateway_notify_cbs
# 2. Add plugin check in check_all_command_guards

with open(target, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the line with _gateway_notify_cbs definition
insert_point_1 = None
for i, line in enumerate(lines):
    if '_gateway_notify_cbs: dict[str, object] = {}' in line:
        insert_point_1 = i + 1
        break

if insert_point_1 is None:
    print('ERROR: Could not find _gateway_notify_cbs insertion point')
    sys.exit(1)

# Insert the plugin approval channel code
plugin_code = '''
# Plugin approval channel — allows plugins to provide approval responses
# (e.g. via Toast notification buttons) before falling back to CLI/gateway.
_plugin_approval_handler = None  # callable(command, description, timeout) -> str | None


def set_plugin_approval_handler(handler) -> None:
    """Register a plugin approval handler.

    The handler signature is ``handler(command: str, description: str,
    timeout: int) -> str | None`` where the return value is one of
    ``"once"``, ``"session"``, ``"always"``, ``"deny"``, or ``None``
    (meaning "no response, fall through to CLI/gateway").
    """
    global _plugin_approval_handler
    _plugin_approval_handler = handler


def clear_plugin_approval_handler() -> None:
    """Unregister the plugin approval handler."""
    global _plugin_approval_handler
    _plugin_approval_handler = None

'''

lines.insert(insert_point_1, plugin_code)

# Find the insertion point for the plugin check in check_all_command_guards
# Look for 'combined_desc = "; ".join(desc for _, desc, _ in warnings)'
insert_point_2 = None
for i, line in enumerate(lines):
    if 'combined_desc = "; ".join(desc for _, desc, _ in warnings)' in line:
        insert_point_2 = i
        break

if insert_point_2 is None:
    print('ERROR: Could not find check_all_command_guards insertion point')
    sys.exit(1)

# Insert the plugin approval check after combined_desc
plugin_check = '''
    # --- Plugin approval channel ---
    # Try the plugin handler first (e.g. Toast notification with buttons).
    if _plugin_approval_handler is not None:
        try:
            plugin_timeout = _get_approval_timeout() or 60
            plugin_choice = _plugin_approval_handler(command, combined_desc, plugin_timeout)
            if plugin_choice in (\"once\", \"session\", \"always\", \"deny\"):
                logger.info(\"Plugin approval handler returned: %s (command: %s)\",
                            plugin_choice, command[:100])
                if plugin_choice == \"deny\":
                    return {
                        \"approved\": False,
                        \"message\": f\"BLOCKED: Plugin denied this command (matched '{combined_desc}' pattern).\",
                        \"pattern_key\": primary_key,
                        \"description\": combined_desc,
                    }
                if plugin_choice == \"session\":
                    for key, _, _ in warnings:
                        approve_session(session_key, key)
                elif plugin_choice == \"always\":
                    for key, _, is_tirith in warnings:
                        approve_session(session_key, key)
                        if not is_tirith:
                            approve_permanent(key)
                    save_permanent_allowlist(_permanent_approved)
                return {\"approved\": True, \"message\": None,
                        \"user_approved\": True, \"description\": combined_desc}
        except Exception as exc:
            logger.warning(\"Plugin approval handler failed: %s — falling through\", exc)

'''

# Find the line after combined_desc assignment
insert_point_2 += 1  # Insert after the combined_desc line
lines.insert(insert_point_2, plugin_check)

# Write the modified file
with open(target, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print('Patch applied successfully!')
print('Please restart Hermes for changes to take effect.')
"

echo.
echo Done! Restart Hermes to activate the plugin approval channel.
pause
