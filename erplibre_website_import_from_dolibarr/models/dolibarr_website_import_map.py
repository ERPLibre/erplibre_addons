# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Identity table: which Odoo record a Dolibarr source item became.

The identity lives here only, never in module xmlids (removed on module
update) nor in view keys (regenerated when a page is renamed).
"""

from odoo import fields, models

KINDS = [
    ("blog", "Blog"),
    ("page", "Page"),
    ("post", "Blog post"),
    ("media", "Media"),
    ("css", "Site CSS"),
    ("js", "Site JavaScript"),
    ("head_view", "Head view"),
    ("blog_style_view", "Blog style view"),
    ("menu", "Menu entry"),
    ("redirect", "Redirect"),
]


class DolibarrWebsiteImportMap(models.Model):
    _name = "dolibarr.website.import.map"
    _description = "Dolibarr website import identity"
    _order = "kind, ref"

    website_id = fields.Many2one("website", required=True, ondelete="cascade")
    source_key = fields.Char(required=True)
    kind = fields.Selection(KINDS, required=True)
    ref = fields.Char(required=True, default="")
    res_model = fields.Char(required=True)
    res_id = fields.Many2oneReference(model_field="res_model")
    content_hash = fields.Char()
    written_hash = fields.Char()
    last_import_id = fields.Many2one(
        "dolibarr.website.import", ondelete="set null", index=True
    )
    last_action = fields.Selection(
        [
            ("created", "Created"),
            ("updated", "Updated"),
            ("unchanged", "Unchanged"),
            ("recreated", "Recreated"),
            ("kept_local", "Local edit kept"),
        ]
    )

    _sql_constraints = [
        (
            "identity_unique",
            "UNIQUE(website_id, source_key, kind, ref)",
            "One record per source item.",
        ),
    ]
