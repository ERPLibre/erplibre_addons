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
    "depends": [
        "erplibre_info",
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
