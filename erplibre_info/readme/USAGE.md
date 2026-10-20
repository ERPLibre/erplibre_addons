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

Pull the code:

1. *Settings › ERPLibre › Pull the code*, or **Pull** on a snapshot
   repository of the running Odoo version, opens a wizard: the mode, the
   strategy and, from a repository, that repository alone.
   - *Manifest*: the ERPLibre root pulls the branch it tracks, the local
     manifest is regenerated (frozen or not, as it is now), then each
     repository integrates the target of its new entry, without `repo
     sync`. A detached repository with no commit of its own switches to
     its target. A new repository of the manifest, cloned only when it is
     allowed, comes from a `repo sync` restricted to its path.
   - *Branches*: each repository pulls the branch it tracks; a detached
     HEAD is skipped.
2. The dry run only fetches. Its report shows, per repository, the
   incoming commits, its own commits, a modified tree (stashed then
   reapplied), the shallow clones, and in manifest mode the manifest
   changes, the new repositories and the Python dependencies that change.
   Ignored local files that the target starts tracking are listed: the
   pull copies them into its pass before git overwrites them.
3. **Apply the pull** opens the confirmation: tick the box and type the
   database name; two more boxes allow deepening the shallow clones
   (it downloads history) and cloning the new repositories. Each
   repository gets a backup branch `<branch>_avant_pull_<stamp>` on its
   HEAD, then integrates its target. A rebase or merge that conflicts is
   aborted and the repository put back where it was. If a remote or a
   HEAD moved since the dry run, nothing is written and a new dry run is
   needed. The pass is recorded under `tasks/git_repo_pull/`. It runs
   within a time budget below `erplibre_info.long_timeout`: what it could
   not start in time is reported as such. A call killed anyway keeps the
   restart blocked until a new dry run, and its backups are listed.
4. After the apply step, a snapshot is taken and the modules to upgrade
   are listed, as for a fetch + rebase. When the Python dependencies
   changed, **Install the Python dependencies** runs `poetry install
   --no-root` in the Odoo virtual environment; the restart buttons stay
   available to restart without installing. A repository that could not
   be put back blocks every restart button until it is fixed in a
   terminal and a new pull dry run is done.
5. The *Backups* page of the apply run lists the backup branches:
   **Restore** moves a repository back to its backup (after the same
   confirmation; refused when commits were made on it since the pull),
   **Delete** removes the branch, restored or not.
