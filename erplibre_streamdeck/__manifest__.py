# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "ERPLibre Stream Deck",
    "version": "18.0.1.4.0",
    "category": "Productivity",
    "summary": "Inventory of the employees' workstations and Stream Decks.",
    "description": (
        "Inventory and monitoring of the employees' workstations and Elgato "
        "Stream Decks, fed by the ERPLibre Home GNOME extension. A "
        "workstation enrolls with a pairing code, an API key or a login, "
        "then reports its decks, its deck service and their events. "
        "Managers see the whole fleet, get an activity when a deck service "
        "fails or a workstation goes silent, and pilot the deck settings "
        "and home-screen key layouts through profiles."
    ),
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
        "data/streamdeck_catalog_data.xml",
        "wizard/streamdeck_pairing_wizard_views.xml",
        "views/streamdeck_workstation_views.xml",
        "views/streamdeck_device_views.xml",
        "views/streamdeck_event_views.xml",
        "views/streamdeck_config_views.xml",
        "views/streamdeck_key_layout_views.xml",
        "wizard/streamdeck_config_policy_views.xml",
        "views/res_config_settings_views.xml",
        "views/streamdeck_menus.xml",
    ],
    "installable": True,
}
