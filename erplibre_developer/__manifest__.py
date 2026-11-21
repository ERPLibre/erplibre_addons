# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "ERPLibre developer",
    "version": "18.0.1.0.0",
    "author": "TechnoLibre",
    "website": "https://technolibre.ca",
    "license": "AGPL-3",
    "category": "Extra Tools",
    "summary": "Developer panel: views, fields, modules and code of the page",
    "description": """
ERPLibre developer
==================

A **Developer panel** in the debug menu of every view: a drawer beside the
page that shows which modules shape it, and follows the views the user
opens.

* **Views & inheritance**: the view shown, every view combined into it in
  the order Odoo applies them (module, priority, XPath and position, file
  and line), then the combined arch.
* **Fields & modules**: the module and the file line that define each
  field of the view, and the modules that override it, read from the
  classes of the running server.
* **Code & repository**: the path, versions and git repository of each
  module involved, the state of that repository from the last snapshot of
  *ERPLibre info - Git* or read on demand, and its recent commits.
* **Dev actions**: the prerequisites of the server actions, the modules
  of the page with those to upgrade checked, the upgrade of the checked
  modules (the confirmation of *ERPLibre info* marks them and restarts
  the Odoo server, so the upgrade runs at the next start with the code on
  disk), the reload of the assets and the recent runs.

Hovering a view or a field highlights it in the page; **Inspect** selects
the field clicked in the page.

The panel is shown to the Settings administrators in developer mode. The
upgrade is a server action of *ERPLibre info*: it needs
``erplibre_info_allow_server_actions = True`` in the Odoo configuration
file.
""",
    "depends": [
        "erplibre_info_git",
        "web",
    ],
    "assets": {
        "web.assets_backend": [
            "erplibre_developer/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "erplibre_developer/static/tests/**/*.test.js",
        ],
        "web.assets_tests": [
            "erplibre_developer/static/tests/tours/**/*",
        ],
    },
    "installable": True,
}
