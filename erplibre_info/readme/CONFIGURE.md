The ERPLibre checkout is found above the running Odoo. Set the system
parameter `erplibre_info.root` to another directory if needed. The
parameters `erplibre_info.timeout` (default 120 s) and
`erplibre_info.long_timeout` (default 3600 s, fetch + rebase) bound each
script call.

The server actions, the restart and those of the modules that extend this
one, need all three of:

- `erplibre_info_allow_server_actions = True` in the `[options]` section
  of the Odoo configuration file;
- the group *Administration / Settings*;
- the developer mode.

The runs execute with `queue_job` when it is installed and loaded as a
server-wide module, otherwise through the cron, triggered once.
