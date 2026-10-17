The button appears when a DevOps workspace marked « ME » has a PyCharm
configuration. Opening a file is a server action of *ERPLibre info*: it
needs `erplibre_info_allow_server_actions = True` in the Odoo
configuration file, the Settings group and the developer mode.

The path is passed to the PyCharm command line of *erplibre_devops*, a
shell line inside a single-quoted terminal command: a path made of
anything else than letters, digits and `._/+-` is refused, and the error
gives `path:line` to open by hand.
