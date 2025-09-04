{
    "name": "ERPLibre website generator from CRM",
    "version": "17.0.1.0.0",
    "author": "TechnoLibre",
    "license": "AGPL-3",
    "website": "https://technolibre.ca",
    "application": True,
    "data": [
        "security/ir.model.access.csv",
        "views/crm_website_generator.xml",
        "views/crm_lead_views.xml",
        "views/res_config_settings_views.xml",
        "views/wizard_crm_generate_website.xml",
    ],
    "depends": [
        "erplibre_website_cloudflare_nginx",
        "crm",
        "sale",
        "website_sale",
    ],
    "installable": True,
}
