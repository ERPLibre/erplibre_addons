# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "ERPLibre info - Git",
    "version": "18.0.1.0.0",
    "author": "TechnoLibre",
    "website": "https://technolibre.ca",
    "license": "AGPL-3",
    "category": "Extra Tools",
    "summary": "Snapshots of the ERPLibre code, read from the git clones",
    "depends": [
        "erplibre_info",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/erplibre_code_snapshot_repo_views.xml",
        "views/erplibre_code_snapshot_module_views.xml",
        "views/erplibre_code_snapshot_views.xml",
        "views/erplibre_code_cross_version_views.xml",
        "views/erplibre_code_run_views.xml",
        "views/res_config_settings_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
}
