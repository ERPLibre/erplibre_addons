# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

DEFAULT_MAX_HIDDEN_THEMES = 2


class LinkupRefletSecret(models.Model):
    """The hidden themes of a precision, apart from the reflection.

    No group has any access right on this model: only the server methods
    read it, under ``sudo``. A field of ``linkup.reflet`` would leak the
    themes through a search, a count or a grouping even with its reading
    restricted; a separate model without access closes all of them at once.
    The author gets the themes through
    ``linkup.reflet.revealed_category_ids``, everybody once the guess is
    made.
    """

    _name = "linkup.reflet.secret"
    _description = "LinkUp hidden themes of a precision"

    reflet_id = fields.Many2one(
        "linkup.reflet", required=True, index=True, ondelete="cascade"
    )
    category_ids = fields.Many2many("linkup.category", string="Hidden themes")
    primary_category_id = fields.Many2one(
        "linkup.category", string="Main theme", ondelete="restrict"
    )

    _sql_constraints = [
        (
            "reflet_unique",
            "UNIQUE(reflet_id)",
            "A precision has a single set of hidden themes.",
        ),
    ]

    @api.model
    def _linkup_max_hidden_themes(self):
        """Maximum number of hidden themes of a precision (setting)."""
        value = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("linkup.max_hidden_themes")
        )
        try:
            return int(value) if value else DEFAULT_MAX_HIDDEN_THEMES
        except ValueError:
            return DEFAULT_MAX_HIDDEN_THEMES

    @api.constrains("category_ids", "primary_category_id")
    def _check_themes(self):
        maximum = self._linkup_max_hidden_themes()
        for secret in self:
            if len(secret.category_ids) > maximum:
                raise ValidationError(
                    _(
                        "A precision hides at most %(count)s themes.",
                        count=maximum,
                    )
                )
            if (
                secret.primary_category_id
                and secret.primary_category_id not in secret.category_ids
            ):
                raise ValidationError(
                    _("The main theme must be one of the hidden themes.")
                )
