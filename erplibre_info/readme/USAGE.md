- *Settings › ERPLibre*: summary of the last snapshot, **Capture now**
  (always stores a new snapshot) and **History**.
- *Settings › Technical › ERPLibre* (developer mode): code snapshots,
  their repositories and installed modules, the comparisons across Odoo
  versions and the runs.
- On a snapshot repository whose HEAD moved, **Load the commits** lists
  the commits since the previous snapshot. **Other Odoo versions**, on a
  repository or an installed module, compares it with the other trees.

Fetch + rebase:

1. *Settings › ERPLibre › Fetch + rebase from upstream* queues a dry run:
   it adds the upstream remotes, fetches them and diagnoses every fork.
   The run shows the verdict of each fork. The forks with a predicted
   conflict are left to the TODO menu (`make todo`).
2. **Apply** on the dry run opens a confirmation: tick the box and type
   the database name. Each fork without predicted conflict is rebased in
   a new dated branch; a fork that conflicts anyway is put back where it
   was. The pass is recorded under `tasks/git_repo_upgrade/` of the
   checkout, as the TODO menu does. Nothing is pushed.
   The apply step rebases onto the upstream commits the dry run showed:
   if the upstream or a fork moved since, nothing is written and a new
   dry run is needed. Only the last dry run can be applied.
3. After the apply step, a snapshot is taken and the run lists the
   installed modules to upgrade: those with a file changed by the apply,
   whatever their version, and those whose version on disk differs from
   the database. **Upgrade the modules and restart** marks them to
   upgrade and restarts the server: the upgrade runs at the next start,
   with the new code. **Restart the server** restarts without upgrading.
