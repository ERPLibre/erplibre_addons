# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "ERPLibre studio",
    "version": "18.0.1.1.0",
    "author": "TechnoLibre",
    "website": "https://technolibre.ca",
    "license": "AGPL-3",
    "category": "Extra Tools",
    "summary": "Drag-and-drop editor of views, applied to the database",
    "depends": [
        "erplibre_developer",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/erplibre_studio_project_views.xml",
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
