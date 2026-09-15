# Copyright 2025 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "ERPLibre DevOps Sync external data",
    "category": "Tools",
    "summary": "Support sync external data into ERPLibre_devops to generate data",
    "version": "18.0.1.0.0",
    "author": "Mathieu Benoit",
    "license": "AGPL-3",
    "website": "https://erplibre.ca",
    "application": True,
    "depends": [
        "code_generator",
        "erplibre_devops",
        "erplibre_sync_external_data",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/devops_cg_field.xml",
        "views/devops_cg_sync_bind.xml",
        "views/devops_cg_model.xml",
        "wizards/devops_plan_action_wizard.xml",
    ],
    "auto_install": True,
    "installable": True,
}
