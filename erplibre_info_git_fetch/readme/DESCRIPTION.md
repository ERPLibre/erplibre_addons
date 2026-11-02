The server actions that write the ERPLibre code: a fetch + rebase of the
forks from their upstream, and the pull of the deployed code with
`script/git/repo_pull.py`. Each time a dry run first, then an apply step
after a double validation. Nothing is ever pushed. After an apply, the
restart of *erplibre_info* upgrades the modules whose code changed.

The module writes the git clones of the checkout: it installs only on an
Odoo server started with `--dev`, and every one of its actions, the
background step included, is refused on a server running without it.
