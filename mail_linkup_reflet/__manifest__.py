# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

{
    "name": "LinkUp — Reflections in Discuss",
    "summary": "Members restricted to Discuss, where they exchange"
    " reflections of real-life conversations",
    "version": "18.0.1.0.0",
    "author": "R. Michaud, S. Bassetto (Polytechnique Montréal, CIMAR LAB),"
    " Mathieu Benoit (TechnoLibre)",
    "website": "https://erplibre.ca",
    "category": "Productivity/Discuss",
    "license": "AGPL-3",
    "depends": [
        "mail",
        "auth_signup",
    ],
    "data": [
        "security/linkup_security.xml",
        "security/ir.model.access.csv",
        "security/linkup_rules.xml",
        "views/linkup_menus.xml",
        "views/res_config_settings_views.xml",
        "views/linkup_invitation_templates.xml",
        "data/linkup_data.xml",
        "data/linkup_invitation_data.xml",
        "data/linkup_category_data.xml",
        "data/linkup_cron.xml",
    ],
    "demo": [
        "demo/linkup_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "mail_linkup_reflet/static/src/**/*",
            # The dark tints are compiled in the dark bundle only.
            ("remove", "mail_linkup_reflet/static/src/**/*.dark.scss"),
            # The public pages load the frontend bundle.
            ("remove", "mail_linkup_reflet/static/src/public/**/*"),
        ],
        "web.assets_frontend": [
            "mail_linkup_reflet/static/src/public/**/*",
        ],
        "web.assets_web_dark": [
            "mail_linkup_reflet/static/src/**/*.dark.scss",
        ],
        "web.assets_unit_tests": [
            "mail_linkup_reflet/static/tests/**/*",
            ("remove", "mail_linkup_reflet/static/tests/tours/**/*"),
        ],
        "web.assets_tests": [
            "mail_linkup_reflet/static/tests/tours/**/*",
        ],
    },
    "uninstall_hook": "uninstall_hook",
    "installable": True,
    "application": False,
    "auto_install": False,
}
