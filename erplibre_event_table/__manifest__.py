# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
{
    "name": "Event Rotating Tables",
    "version": "18.0.1.0.0",
    "summary": "Seat event participants at rotating tables over several rounds",
    # Rendered as RST for the Apps page on a non-application module (see
    # `application` below). Keep every paragraph plain and unindented: a
    # "---" separator (three characters, short of RST's four-character
    # transition rule), a line indented without a blank line before it,
    # or any bulleted/numbered list turns back into a docutils warning.
    "description": """
English

Configure tables and generate several seating combinations for an event,
each compared against a proven minimum for indicators such as colleague
pairs, repeated meetings, table returns and people met. Choose a
combination and refine it by hand on an interactive floor plan: move or
resize tables, drag participants between seats, or seat a latecomer
waiting in the tray.

Participants can come from event registrations, from other contacts, or
be typed in directly. Once seating is set, print participant cards and
table sheets, or email each participant their assigned tables.

Français

Configurez les tables et générez plusieurs combinaisons pour un
événement, chacune comparée à un minimum prouvé pour des indicateurs
tels que les paires de collègues, les rencontres répétées, les retours
à une table et les personnes rencontrées. Choisissez une combinaison et
retouchez-la à la main sur un plan de salle interactif : déplacez ou
redimensionnez les tables, glissez les participants d'un siège à
l'autre, ou asseyez un retardataire qui attend dans la réserve.

Les participants peuvent provenir des inscriptions à l'événement,
d'autres contacts, ou être saisis directement. Une fois le placement
fait, imprimez les cartes des participants et les feuilles de table, ou
envoyez à chaque participant ses tables par courriel.
""",
    "author": "TechnoLibre",
    "website": "https://technolibre.ca",
    "category": "Marketing/Events",
    "license": "AGPL-3",
    "depends": ["event", "mail", "web"],
    "data": [
        "security/ir.model.access.csv",
        "security/event_table_security.xml",
        "data/mail_template_data.xml",
        "report/event_table_reports.xml",
        "report/event_table_report_templates.xml",
        "wizards/event_table_configure_wizard_views.xml",
        "wizards/event_table_participant_wizard_views.xml",
        "wizards/event_table_pin_generate_wizard_views.xml",
        "views/event_table_plan_views.xml",
        "views/event_table_combination_views.xml",
        "views/event_table_assignment_views.xml",
        "views/event_type_views.xml",
        "views/event_event_views.xml",
        "views/res_partner_views.xml",
        "views/event_table_menus.xml",
    ],
    "demo": [
        "data/event_table_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "erplibre_event_table/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "erplibre_event_table/static/tests/**/*",
        ],
    },
    "installable": True,
    "application": False,
}
