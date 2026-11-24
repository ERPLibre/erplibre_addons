# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

{
    "name": "LinkUp — Points and gamification",
    "summary": "Maps LinkUp events to the"
    " gamification karma, ranks and badges",
    "version": "18.0.1.0.0",
    "author": "R. Michaud, S. Bassetto (Polytechnique Montréal, CIMAR LAB),"
    " Mathieu Benoit (TechnoLibre)",
    "website": "https://erplibre.ca",
    "category": "Productivity/Discuss",
    "license": "AGPL-3",
    "depends": [
        "mail_linkup_reflet",
        "gamification",
    ],
    "data": [
        "security/ir.model.access.csv",
        "security/linkup_points_rules.xml",
        "data/linkup_points_rule_data.xml",
        "data/gamification_data.xml",
        "data/linkup_points_cron.xml",
        "views/linkup_points_views.xml",
        "views/res_config_settings_views.xml",
        "views/linkup_my_points_views.xml",
    ],
    "demo": [
        "demo/linkup_points_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "mail_linkup_gamification/static/src/**/*",
            # The dark tints are compiled in the dark bundle only.
            ("remove", "mail_linkup_gamification/static/src/**/*.dark.scss"),
        ],
        "web.assets_web_dark": [
            "mail_linkup_gamification/static/src/**/*.dark.scss",
        ],
        "web.assets_unit_tests": [
            "mail_linkup_gamification/static/tests/**/*",
            ("remove", "mail_linkup_gamification/static/tests/tours/**/*"),
        ],
        "web.assets_tests": [
            "mail_linkup_gamification/static/tests/tours/**/*",
        ],
    },
    "uninstall_hook": "uninstall_hook",
    "installable": True,
    "application": False,
    "auto_install": False,
}
