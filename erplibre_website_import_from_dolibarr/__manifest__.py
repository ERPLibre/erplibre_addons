# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
# data/dolibarr_langs/ bundles unmodified Dolibarr .lang files under
# GPL-3.0-or-later: see data/dolibarr_langs/README.md.

{
    "name": "Website import from Dolibarr",
    "version": "18.0.1.0.0",
    "category": "Website",
    "summary": "Import a Dolibarr website export into an Odoo website",
    "author": "TechnoLibre",
    "license": "AGPL-3",
    "website": "https://technolibre.ca",
    "depends": [
        "website",
        "website_blog",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/templates.xml",
    ],
    "application": False,
    "installable": True,
}
