# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "ERPLibre studio",
    "version": "18.0.1.2.0",
    "author": "TechnoLibre",
    "website": "https://technolibre.ca",
    "license": "AGPL-3",
    "category": "Extra Tools",
    "summary": "Drag-and-drop editor of views, applied to the database",
    "description": """
ERPLibre studio
===============

A drag-and-drop editor of views whose changes are recorded in a **studio
project**, applied to the database, and can become a module.

* **Views**: form, list, kanban, search, pivot and graph views, and
  timeline views once *web_timeline* is installed. **Customize this view**, in the
  debug menu or the *Developer panel*, opens the editor on the view of the
  page. Fields move by drag and drop; the palette adds existing fields and
  new ``x_`` fields, the side panel edits their properties. **Add a view**
  gives a model a view of a type it lacks.
* **New models**: ``x_`` models with their views, action, menu and access
  rights, in an app of the project or under an existing menu, with a
  chatter when *mail* is installed; one2many and many2many relations.
* **Security**: groups per app, an access grid next to the rights the
  other modules give, record rules checked against their model.
* **Draft, Preview, Apply**: each change is a draft; **Preview** shows the
  view with the draft, a model not created yet is simulated in the
  browser; **Apply** reviews the draft, item by item, then writes it to
  the database, where every user sees it; **Discard** goes back to the last Apply; **Revert** removes
  what the project created, the records of its models included. Revert,
  and an Apply that removes records, values or group members, first list
  what leaves the database and ask for confirmation.

The editor is shown to the Settings administrators in developer mode.
This module does not depend on *code_generator*: *ERPLibre studio
generate* writes a project as a module.
""",
    "depends": [
        "erplibre_developer",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/erplibre_studio_project_views.xml",
        "views/base_module_uninstall_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "erplibre_studio/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "erplibre_studio/static/tests/**/*.test.js",
        ],
        "web.assets_tests": [
            "erplibre_studio/static/tests/tours/**/*",
        ],
    },
    "installable": True,
}
