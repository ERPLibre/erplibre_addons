# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "ERPLibre info - Git fetch",
    "version": "18.0.1.1.0",
    "author": "TechnoLibre",
    "website": "https://technolibre.ca",
    "license": "AGPL-3",
    "category": "Extra Tools",
    "summary": "Fetch + rebase, pull and return to a snapshot of the ERPLibre code",
    "depends": [
        "erplibre_info_git",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/erplibre_code_snapshot_repo_views.xml",
        "views/erplibre_code_run_views.xml",
        "views/erplibre_code_snapshot_views.xml",
        "views/erplibre_code_stash_views.xml",
        "wizards/erplibre_code_confirm_wizard_views.xml",
        "wizards/erplibre_code_pull_wizard_views.xml",
        "wizards/erplibre_code_revert_wizard_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "assets": {
        "web.assets_tests": [
            "erplibre_info_git_fetch/static/tests/tours/*.js",
        ],
    },
    "post_init_hook": "post_init_hook",
    "installable": True,
}
