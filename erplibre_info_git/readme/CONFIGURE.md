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
