Adds a **Claude Code** tab to Odoo project tasks, allowing developers to
launch an AI coding agent directly from a task description.

The agent is powered by the `claude-agent-sdk` (Anthropic) and runs
asynchronously in a background thread, streaming its output back to the
task form in real time.
