# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "ERPLibre DevOps Requirement",
    "version": "18.0.1.0.0",
    "category": "Project",
    "summary": (
        "Track the software requirements of an implementation project in "
        "MoSCoW terms, by domain and by phase."
    ),
    "author": "TechnoLibre",
    "website": "https://erplibre.ca",
    "license": "AGPL-3",
    "application": True,
    # Le module ne livre AUCUN requis, AUCUN domaine et AUCUNE phase : ces
    # vocabulaires appartiennent au projet qui l'installe.
    "depends": [
        "base",
        "mail",
    ],
    "data": [
        "security/ir.model.access.csv",
    ],
    "installable": True,
}
