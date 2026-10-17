Install this module on development databases only. *code_generator*
installs only on a server started with `--dev`, and its installation
drops the database constraint that keeps the names of custom fields
starting with `x_`: the server of the database runs with `--dev`.

**Generate the module** and **Install the generated module** write to the
disk of the server: they need the Settings group, the developer mode and
`erplibre_info_allow_server_actions = True` in the `[options]` section of
the Odoo configuration file, as the server actions of *ERPLibre info*.

The destinations are the addons repositories of the running Odoo version
listed by the last *ERPLibre info* snapshot. The system parameter
`erplibre_studio.default_destination` gives the default one, as a path
relative to the ERPLibre checkout (for example
`odoo18.0/addons/<repository>`).
