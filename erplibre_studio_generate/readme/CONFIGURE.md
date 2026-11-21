Install this module on development databases only. *code_generator*
installs only on a server started with `--dev`, and its installation
drops the database constraint that keeps the names of custom fields
starting with `x_`: the server of the database runs with `--dev`.

**Generate the module** and **Install the generated module** write to the
disk of the server: they need the Settings group, the developer mode and
`erplibre_info_allow_server_actions = True` in the `[options]` section of
the Odoo configuration file, as the server actions of *ERPLibre info*.

The destinations are the directories of the `addons_path` of the server,
read from its configuration: those that exist and the server can write
into, without the addons of Odoo itself. A directory inside the ERPLibre
checkout shows as its path relative to the checkout, any other as its
absolute path. The system parameter `erplibre_studio.default_destination`
gives the default one, written the same way (for example
`odoo18.0/addons/<repository>`).
