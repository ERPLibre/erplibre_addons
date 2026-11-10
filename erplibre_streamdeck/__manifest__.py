# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "ERPLibre Stream Deck",
    "version": "18.0.1.1.0",
    "category": "Productivity",
    "summary": "Inventory of the employees' workstations and Stream Decks.",
    "author": "TechnoLibre",
    "website": "https://erplibre.ca",
    "license": "AGPL-3",
    "application": False,
    "depends": [
        "base",
    ],
    "data": [
        "security/streamdeck_security.xml",
        "security/ir.model.access.csv",
        "security/streamdeck_rules.xml",
    ],
    "installable": True,
}
