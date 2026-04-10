All settings are in **Project ‣ Configuration ‣ Settings ‣ Claude Code**.

## Authentication

### Option A — Anthropic API key (recommended for servers)

1. Get your key from <https://console.anthropic.com/> (format:
   `sk-ant-api03-…`).
2. Paste it in **Anthropic API Key**. The value is stored encrypted in
   `ir.config_parameter` and injected as `ANTHROPIC_API_KEY` into the
   agent process at runtime.

### Option B — CLI session (interactive login)

On the server, as the user that runs Odoo:

```bash
claude login
```

Credentials are stored in `~/.claude/`. Leave the API key field empty in
Odoo; the SDK will pick up the session automatically.

## Claude binary path (optional)

If `claude` is not in the PATH seen by the Odoo process, enter the
absolute path in **Claude binary path** (e.g. `/usr/local/bin/claude`).

```bash
# find the path
which claude
```

Leave empty to rely on automatic PATH detection.

## Task-level fields

On each project task, in the **Claude Code** tab:

| Field | Description |
|---|---|
| **ERPLibre workspace** | Absolute path used as `cwd` for the agent (e.g. `/home/user/erplibre`) |
| **Working directory** | Fallback `cwd` if the workspace field is empty |
| **Module name** | Odoo module to develop (e.g. `sale_custom_discount`) |
