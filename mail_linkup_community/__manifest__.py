# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

{
    "name": "LinkUp — Public community",
    "summary": "Public sign-up, consents, profile,"
    " moderation and personal data",
    "version": "18.0.1.0.0",
    "author": "R. Michaud, S. Bassetto (Polytechnique Montréal, CIMAR LAB),"
    " Mathieu Benoit (TechnoLibre)",
    "website": "https://erplibre.ca",
    "category": "Productivity/Discuss",
    "license": "AGPL-3",
    "depends": [
        "mail_linkup_reflet",
        "mail_linkup_gamification",
        # The proof of work of the signup entries, inactive until the
        # website holds an ALTCHA key (see Configuration in README.rst).
        "website_altcha",
    ],
    "data": [
        "security/ir.model.access.csv",
        "security/linkup_community_rules.xml",
        "data/linkup_community_data.xml",
        "views/linkup_signup_templates.xml",
        "views/linkup_community_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "mail_linkup_community/static/src/**/*",
            # The dark tints are compiled in the dark bundle only.
            ("remove", "mail_linkup_community/static/src/**/*.dark.scss"),
            # The public pages load the frontend bundle.
            ("remove", "mail_linkup_community/static/src/public/**/*"),
        ],
        "web.assets_frontend": [
            "mail_linkup_community/static/src/public/**/*",
        ],
        "web.assets_web_dark": [
            "mail_linkup_community/static/src/**/*.dark.scss",
        ],
        "web.assets_unit_tests": [
            "mail_linkup_community/static/tests/**/*",
            ("remove", "mail_linkup_community/static/tests/tours/**/*"),
        ],
        "web.assets_tests": [
            "mail_linkup_community/static/tests/tours/**/*",
        ],
    },
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
    "auto_install": False,
}
