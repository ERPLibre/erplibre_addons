# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

{
    "name": "LinkUp — Network view",
    "summary": "Self-centred graph of a member's links, with rankings",
    "version": "18.0.1.0.0",
    "author": "R. Michaud, S. Bassetto (Polytechnique Montréal, CIMAR LAB),"
    " Mathieu Benoit (TechnoLibre)",
    "website": "https://erplibre.ca",
    "category": "Productivity/Discuss",
    "license": "AGPL-3",
    "depends": [
        "mail_linkup_gamification",
        "mail_linkup_reflet",
    ],
    "data": [
        "views/linkup_network_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "demo": [
        "demo/linkup_network_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "mail_linkup_network/static/src/**/*",
            # The dark tints are compiled in the dark bundle only.
            ("remove", "mail_linkup_network/static/src/**/*.dark.scss"),
        ],
        "web.assets_web_dark": [
            "mail_linkup_network/static/src/**/*.dark.scss",
        ],
        "web.assets_unit_tests": [
            "mail_linkup_network/static/tests/**/*",
            ("remove", "mail_linkup_network/static/tests/tours/**/*"),
        ],
        "web.assets_tests": [
            "mail_linkup_network/static/tests/tours/**/*",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
