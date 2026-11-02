Start the Odoo server with `--dev` (for example `--dev=all`): without it
the installation is refused, and so is every fetch + rebase or pull of a
server restarted without it. Odoo reads `--dev` from the command line only:
a `dev_mode` line of the configuration file is ignored. Write it with its
`=` when other arguments follow, as in a Docker image whose entrypoint
appends the database ones: a bare `--dev` takes the next argument as its
value.

The account that runs Odoo must be able to write the git clones. In a
Docker image, that is the account named by `ERPLIBRE_CODE_OWNER` at build
time, `odoo` by default.

**Pull strategy** (in the *Server actions* setting) is the default way
a repository with commits of its own integrates its target when the
code is pulled: rebase (default), fast-forward only, or merge. The pull
wizard starts with it and lets it change for one pull.

Fetch + rebase and pull need all four of the following; the restart of
*erplibre_info* needs the last three only:

- a server started with `--dev`;
- `erplibre_info_allow_server_actions = True` in the `[options]` section
  of the Odoo configuration file;
- the group *Administration / Settings*;
- the developer mode.
