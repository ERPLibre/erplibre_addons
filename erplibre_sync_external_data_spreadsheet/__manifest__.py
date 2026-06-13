{
    "name": "Sync external data spreadsheet",
    "category": "Uncategorized",
    "version": "18.0.1.0.0",
    "author": "TechnoLibre",
    "license": "AGPL-3",
    "depends": ["erplibre_sync_external_data"],
    "external_dependencies": {
        "python": [
            "openpyxl",
        ],
    },
    "data": [
        "views/sync_data_exec.xml",
    ],
    "installable": True,
}
