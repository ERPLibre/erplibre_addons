The panel is shown to the members of *Administration / Settings*, in
developer mode; the server checks both on every call.

**Upgrade (-u)** and **Open in IDE** are server actions of *ERPLibre
info*: they also need `erplibre_info_allow_server_actions = True` in the
`[options]` section of the Odoo configuration file.

The recent commits come from a `git log` limited to the module directory
and to 20 commits, bounded by the `erplibre_info.timeout` system
parameter.
