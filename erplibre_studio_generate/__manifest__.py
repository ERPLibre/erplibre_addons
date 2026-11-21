# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "ERPLibre studio generate",
    "version": "18.0.1.3.0",
    "author": "TechnoLibre",
    "website": "https://technolibre.ca",
    "license": "AGPL-3",
    "category": "Extra Tools",
    "summary": "Generate the module of an ERPLibre studio project with code_generator",
    "description": """
ERPLibre studio generate
========================

Writes an applied *ERPLibre studio* project as an installable module, with
*code_generator*.

* **Generate the module** writes it into an addons repository of the
  running Odoo version: the new fields, the inherited views under the
  external ids the database already uses, the new models with their views,
  actions, menus and app icons, the groups, access rights and record
  rules, a readme, and the dependencies read from what the project
  touches.
* **Regenerate** rewrites the same module with the next version;
  **Install the generated module** installs it in this database, where it
  takes over the models the project created, records included. From then
  on the module owns them: **Revert** is refused, and uninstalling the
  module deletes these models with their records.
* The generated module depends neither on *code_generator* nor on
  *ERPLibre studio*: it installs on any database.

For development databases only: *code_generator* installs only on a
server started with ``--dev``, and its installation drops the database
constraint that keeps the names of custom fields starting with ``x_``;
this module drops it too at the end of every loading of the modules,
when a module or an update of base added it back.
A new field may then go without ``x_``: this module loads it while the
project is applied, and refuses to be uninstalled until the project is
reverted or its generated module installed. While modules install or
update, the registries set up before this module is loaded log such a
field as « Failed to load field » (ERROR) and skip it; its column and
values stay. A module installed later that defines a field of the same
name takes its column over.
The destinations are the directories of the ``addons_path`` of the
server that it can write into. Writing to the disk needs the
Settings group, the developer mode and
``erplibre_info_allow_server_actions = True`` in the Odoo configuration
file.

Installs by itself when both *erplibre_studio* and *code_generator* are
installed.
""",
    "depends": [
        "erplibre_studio",
        "code_generator",
    ],
    "data": [
        "views/erplibre_studio_project_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "auto_install": True,
    "installable": True,
}
