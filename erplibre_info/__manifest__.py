# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "ERPLibre info",
    "version": "12.0.1.0.0",
    "author": "TechnoLibre",
    "website": "https://technolibre.ca",
    "license": "AGPL-3",
    "category": "Extra Tools",
    "summary": "INSTALL ERPLibre info",
    "description": """
ERPLibre info
=============
Show information of your ERPLibre in settings app.

""",
    "depends": [
        "web_settings_dashboard",
    ],
    "data": [],
    "qweb": [
        "static/src/xml/*.xml",
    ],
    "installable": True,
}
