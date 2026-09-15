{
    "name": "Sync External Data — Test",
    "version": "18.0.1.0.0",
    "author": "TechnoLibre",
    "license": "AGPL-3",
    "category": "Tests",
    "depends": [
        "erplibre_sync_external_data",
        "crm",
        "sale",
        "project",
        "account",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/sync_model_data.xml",
    ],
    "installable": True,
    "auto_install": False,
}
