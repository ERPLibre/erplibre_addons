{
    "name": "ERPLibre configure website Cloudflare and Nginx",
    "version": "16.0.1.0",
    "author": "TechnoLibre",
    "license": "AGPL-3",
    "website": "https://technolibre.ca",
    "application": True,
    "data": [
        "security/ir.model.access.csv",
        "views/res_config_settings_views.xml",
    ],
    "depends": ["website"],
    "external_dependencies": {"python": ["requests", "tldextract"]},
    "installable": True,
}
