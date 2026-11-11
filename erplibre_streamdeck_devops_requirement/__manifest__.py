# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "ERPLibre Stream Deck DevOps Requirement",
    "version": "18.0.1.2.0",
    "category": "Project",
    "summary": (
        "Requirements of the ERPLibre Stream Deck, with the repository "
        "tests that prove them."
    ),
    "author": "TechnoLibre",
    "website": "https://erplibre.ca",
    "license": "AGPL-3",
    "application": False,
    "depends": [
        "erplibre_streamdeck",
        "erplibre_devops_requirement",
    ],
    # Les requis citent leur domaine et les preuves citent leur requis :
    # l'ordre des fichiers suit ces références.
    "data": [
        "data/devops_requirement_category.xml",
        "data/devops_requirement.xml",
        "data/devops_requirement_test.xml",
        "data/requirement_inventory.xml",
        "data/requirement_monitoring.xml",
    ],
    "installable": True,
}
