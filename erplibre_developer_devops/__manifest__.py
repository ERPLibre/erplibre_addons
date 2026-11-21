# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "ERPLibre developer - DevOps IDE",
    "version": "18.0.1.0.0",
    "author": "TechnoLibre",
    "website": "https://technolibre.ca",
    "license": "AGPL-3",
    "category": "Extra Tools",
    "summary": "Open the files of the developer panel in ERPLibre DevOps PyCharm",
    "description": """
ERPLibre developer - DevOps IDE
===============================

Adds an **Open in IDE** button to the files listed by the *Developer
panel* of *ERPLibre developer*: the file opens at its line in the PyCharm
of the *ERPLibre DevOps* workspace marked « ME ». PyCharm starts on the
machine of that workspace, in a terminal, through the JetBrains Toolbox
launcher ``~/.local/share/JetBrains/Toolbox/scripts/pycharm``: a PyCharm
installed elsewhere does not open.

Opening a file is a server action of *ERPLibre info*: it needs
``erplibre_info_allow_server_actions = True`` in the Odoo configuration
file, the Settings group and the developer mode. A path made of anything
else than letters, digits and ``._/+-`` is refused, and the error gives
``path:line`` to open by hand.

Installs by itself when both *erplibre_developer* and *erplibre_devops*
are installed.
""",
    "depends": [
        "erplibre_developer",
        "erplibre_devops",
    ],
    "auto_install": True,
    "installable": True,
}
