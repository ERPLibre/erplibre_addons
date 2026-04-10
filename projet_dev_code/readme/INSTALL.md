## System prerequisites

### 1 — Install the Claude Code CLI

The `claude` binary must be reachable on the Odoo server.

```bash
# via npm (recommended)
npm install -g @anthropic-ai/claude-code

# verify
which claude
claude --version
```

### 2 — Install claude-agent-sdk in the Odoo 18 virtualenv

```bash
source .venv.odoo18/bin/activate
pip install claude-agent-sdk
```

Odoo also checks this dependency at module install time via
`external_dependencies` and will warn if the package is missing.
