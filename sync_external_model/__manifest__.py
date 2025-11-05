{
    "name": "Synchronize models with external Odoo",
    "category": "Tools",
    "version": "17.0.1.0.0",
    "author": "TechnoLibre",
    "license": "AGPL-3",
    "website": "https://technolibre.ca",
    "depends": ["mail", "web_tree_dynamic_colored_field"],
    "external_dependencies": {
        "python": ["odoorpc"],
    },
    "data": [
        "security/ir.model.access.csv",
        "views/sync_db_result.xml",
        "views/sync_db.xml",
        "views/menu.xml",
    ],
    "installable": True,
}
