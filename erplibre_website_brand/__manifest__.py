# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
{
    "name": "ERPLibre Website Brand",
    "version": "18.0.1.0.0",
    "summary": "Footer signature « Built with ERPLibre », eleven styles, "
    "set in the settings",
    "author": "TechnoLibre",
    "website": "https://erplibre.ca",
    "category": "Website",
    "license": "AGPL-3",
    "depends": ["website"],
    "data": [
        "views/brand_promotion_templates.xml",
        "views/res_config_settings_views.xml",
        "views/website_views.xml",
    ],
    "assets": {
        # The backend loads the stylesheet for the preview in the settings.
        "web.assets_frontend": [
            "erplibre_website_brand/static/src/scss/signature.scss",
        ],
        "web.assets_backend": [
            "erplibre_website_brand/static/src/scss/signature.scss",
        ],
    },
    "post_init_hook": "post_init_hook",
    "installable": True,
}
