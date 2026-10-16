Records in the database the state of the ERPLibre code that runs it.

A **code snapshot** stores the ERPLibre version and commit, the Odoo
version, the mode of the checkout (branches or frozen) and, for each
repository of the manifest, its HEAD, its gap to the manifest (revision,
freeze revision, upstream base, state) and, on option, whether its tree
is modified. Each installed module is linked to the repository that holds
its code, with the installed version and the version on disk: a
difference means an upgrade (`-u`) is pending. The commits between two
HEADs of a repository load on demand.

On demand, a repository or a module is compared with the same path under
the other `odoo<V>/` trees of the checkout: presence and version of the
module, our commits still to port (matched by patch-id and subject),
history side by side, diffstat and full diff. The result is cached.

The snapshots are read by the ERPLibre script `script/git/repo_state.py`,
run with the ERPLibre interpreter `.venv.erplibre/bin/python`. It only
reads the clones. The module ships no data: installing it runs nothing.

For an administrator, and only when the Odoo configuration file allows
it, the module also restarts the server and runs a fetch + rebase of the
forks from their upstream: a dry run first, then an apply step after a
double validation. Nothing is ever pushed.
