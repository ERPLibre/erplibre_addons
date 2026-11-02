The common ground of the ERPLibre info modules: the runs, the ERPLibre
settings page and the call of the ERPLibre scripts.

A **code run** is a long action on the code, queued then executed in the
background, by the cron *ERPLibre: code environment* or by `queue_job`.
It records its requester, its log in the requester's language, the JSON
of its script and a report. This module declares one run type, the
server restart; the snapshots come with *erplibre_info_git*, the fetch +
rebase and the pull with *erplibre_info_git_fetch*.

The **server restart** is a server action: after a double validation
(tick the box, type the database name), the server stops and starts
again, optionally after marking modules to upgrade.

*Settings › General Settings › About* shows an ERPLibre block under
Odoo's own: the ERPLibre version, what `make version` prints (Python of
Odoo and of the tooling, Odoo, Poetry, mobile context, extra modules,
version key, installed Odoo versions), the commit of the checkout with its
branch and `git describe --tags`, and the code mode read from the local
manifest: production (frozen commits) or development (branches). The
values come from the files of the checkout and from read-only git
commands bounded by a short timeout; a value that cannot be read shows
as unknown, and opening the page writes nothing.

The scripts are those of the ERPLibre checkout (`script/git/`), run with
its interpreter `.venv.erplibre/bin/python`. The module ships no data:
installing it runs nothing.
