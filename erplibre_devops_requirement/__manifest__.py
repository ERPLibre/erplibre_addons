# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "ERPLibre DevOps Requirement",
    "version": "18.0.1.1.0",
    "category": "Project",
    "summary": (
        "Track the software requirements of an implementation project in "
        "MoSCoW terms, by domain and by phase, through the DevSecOps loop, "
        "with their threats and the tests that prove them."
    ),
    "author": "TechnoLibre",
    "website": "https://erplibre.ca",
    "license": "AGPL-3",
    "application": True,
    # Le module ne livre AUCUN requis, AUCUN domaine et AUCUNE phase : ces
    # vocabulaires appartiennent au projet qui l'installe.
    # `mail` n'est PAS une dépendance : aucun modèle n'hérite de
    # `mail.thread` ni de `mail.activity.mixin`. L'ajouter pour un fil de
    # discussion est une décision à prendre avec le champ qui l'emploie.
    "depends": [
        "base",
    ],
    "data": [
        "security/devops_requirement_security.xml",
        "security/ir.model.access.csv",
        "views/devops_requirement_views.xml",
        "views/devops_requirement_config_views.xml",
        "views/devops_requirement_menus.xml",
    ],
    "installable": True,
}
