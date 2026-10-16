# © 2021-2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "ERPLibre info",
    "version": "18.0.2.0.0",
    "author": "TechnoLibre",
    "website": "https://technolibre.ca",
    "license": "AGPL-3",
    "category": "Extra Tools",
    "summary": "State of the ERPLibre code behind this database",
    "depends": [
        "base_setup",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron.xml",
        "views/erplibre_code_snapshot_repo_views.xml",
        "views/erplibre_code_snapshot_module_views.xml",
        "views/erplibre_code_snapshot_views.xml",
        "views/erplibre_code_cross_version_views.xml",
        "views/erplibre_code_run_views.xml",
        "wizards/erplibre_code_confirm_wizard_views.xml",
        "views/res_config_settings_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
}
