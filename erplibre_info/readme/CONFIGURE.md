Open *Settings › ERPLibre › Odoo modules environment*:

- **Snapshot at server start**: queue one snapshot each time the server
  starts; it runs in the background.
- **Periodic snapshot** and its interval: activate the cron
  *ERPLibre: code environment*. A snapshot is stored only when the code
  or the installed module versions changed.
- **Check modified trees**: also run `git status` in every clone; a
  modified file or an untracked file that no `.gitignore` covers marks
  the clone modified.

A periodic or startup snapshot that cannot run (no ERPLibre checkout,
interpreter missing) is recorded as a failed run, shown in red in the
Settings block.

The ERPLibre checkout is found above the running Odoo. Set the system
parameter `erplibre_info.root` to another directory if needed. The
parameters `erplibre_info.timeout` (default 120 s) and
`erplibre_info.long_timeout` (default 3600 s, fetch + rebase) bound each
script call.

**Pull strategy** (in the *Server actions* setting) is the default way
a repository with commits of its own integrates its target when the
code is pulled: rebase (default), fast-forward only, or merge. The pull
wizard starts with it and lets it change for one pull.

The server actions (restart, fetch + rebase, pull) need all three of:

- `erplibre_info_allow_server_actions = True` in the `[options]` section
  of the Odoo configuration file;
- the group *Administration / Settings*;
- the developer mode.

The long actions run with `queue_job` when it is installed and loaded as
a server-wide module, otherwise through the cron, triggered once.
