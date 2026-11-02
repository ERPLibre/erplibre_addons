# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "ERPLibre info - Git fetch",
    "version": "18.0.1.0.0",
    "author": "TechnoLibre",
    "website": "https://technolibre.ca",
    "license": "AGPL-3",
    "category": "Extra Tools",
    "summary": "Fetch + rebase and pull of the ERPLibre code",
    "depends": [
        "erplibre_info_git",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/erplibre_code_snapshot_repo_views.xml",
        "views/erplibre_code_run_views.xml",
        "wizards/erplibre_code_confirm_wizard_views.xml",
        "wizards/erplibre_code_pull_wizard_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
}
