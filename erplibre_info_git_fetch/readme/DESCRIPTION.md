The server actions that write the ERPLibre code: a fetch + rebase of the
forks from their upstream, the pull of the deployed code with
`script/git/repo_pull.py`, and the return of the code to a snapshot. Each
time a dry run first, then an apply step after a double validation.
Nothing is ever pushed. After an apply, the restart of *erplibre_info*
upgrades the modules whose code changed.

A pull or a return that stashes the modified files of a repository and
keeps the stash records it in the stash history, where it can be
reapplied; a stash is never dropped.

The module writes the git clones of the checkout: it installs only on an
Odoo server started with `--dev`, and every one of its actions, the
background step included, is refused on a server running without it.
