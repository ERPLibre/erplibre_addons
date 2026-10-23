# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Analysis rows: one per source page, with the per-page choice."""

from odoo import fields, models
from odoo.exceptions import UserError


class DolibarrWebsiteImportPage(models.Model):
    _name = "dolibarr.website.import.page"
    _description = "Dolibarr website import analysis row"
    _order = "status, ref"

    import_id = fields.Many2one(
        "dolibarr.website.import",
        required=True,
        ondelete="cascade",
        index=True,
    )
    ref = fields.Char(required=True)
    title = fields.Char()
    lang = fields.Char()
    kind = fields.Selection(
        [("page", "Page"), ("post", "Blog post")], default="page"
    )
    source_url = fields.Char()
    target_url = fields.Char()
    status = fields.Selection(
        [
            ("import", "Import"),
            ("foreign_unlinked", "Other language, no link"),
            ("translation", "Translation"),
            ("container", "Container"),
            ("skipped", "Skipped"),
        ],
        required=True,
    )
    include = fields.Boolean()
    imported_before = fields.Boolean()
    php_plan = fields.Selection(
        [
            ("none", "No PHP"),
            ("translated", "Translated"),
            ("remove", "Will be removed"),
        ],
        default="none",
    )
    php_unknown_blocks = fields.Integer()
    php_removed_bytes = fields.Integer()
    script_count = fields.Integer()
    script_detail = fields.Char()
    translates_ref = fields.Char()

    _sql_constraints = [
        (
            "import_ref_unique",
            "UNIQUE(import_id, ref)",
            "One analysis row per page.",
        ),
    ]

    def write(self, vals):
        """include changes only on foreign rows of a run waiting for review."""
        if "include" in vals:
            self.import_id._check_import_access()
            for row in self:
                if (
                    row.status != "foreign_unlinked"
                    or row.import_id.state != "to_review"
                ):
                    raise UserError(
                        self.env._(
                            "Only pages in another language can be chosen,"
                            " and only while the import waits for review."
                        )
                    )
        return super().write(vals)
