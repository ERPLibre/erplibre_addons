1. Open a project task and go to the **Claude Code** tab.
2. Fill in at minimum one of **ERPLibre workspace** or **Working directory**.
3. Optionally fill **Module name** to give the agent a precise target.
4. Write the development instructions in the standard task **Description**
   field — the agent reads it as its prompt.
5. Click **Start Claude Code**. The status badge turns *In progress* and
   the **Claude Output** field starts filling with the agent's activity.
6. Click **Refresh** to reload the form and see the latest output (there
   is no automatic push; a manual refresh is required).
7. Click **Stop** to interrupt the agent at any time.

The **Session ID** field (visible once the agent finishes) can be used
to resume a session or debug via the `claude` CLI:

```bash
claude --resume <session-id>
```
