# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "ERPLibre Stream Deck",
    "version": "18.0.1.2.0",
    "category": "Productivity",
    "summary": "Inventory of the employees' workstations and Stream Decks.",
    "author": "TechnoLibre",
    "website": "https://erplibre.ca",
    "license": "AGPL-3",
    "application": False,
    "depends": [
        "base",
        "mail",
        "web",
    ],
    "data": [
        "security/streamdeck_security.xml",
        "security/ir.model.access.csv",
        "security/streamdeck_rules.xml",
        "data/streamdeck_activity_types.xml",
        "data/streamdeck_cron.xml",
        "wizard/streamdeck_pairing_wizard_views.xml",
        "views/streamdeck_workstation_views.xml",
        "views/streamdeck_device_views.xml",
        "views/streamdeck_event_views.xml",
        "views/res_config_settings_views.xml",
        "views/streamdeck_menus.xml",
    ],
    "installable": True,
}
