# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import fields, models


class StreamdeckPairingCode(models.Model):
    """A single-use code that enrolls a workstation for `user_id`.

    No group has any right on this model: the pairing wizard creates the
    code in sudo for the current user, and the enrollment route consumes
    it in sudo.
    """

    _name = "streamdeck.pairing.code"
    _description = "Stream Deck pairing code"
    _rec_name = "code"

    code = fields.Char(size=8, required=True)
    user_id = fields.Many2one(
        "res.users",
        string="Employee",
        required=True,
        index=True,
        ondelete="cascade",
    )
    expires_at = fields.Datetime(required=True)
    used = fields.Boolean()

    _sql_constraints = [
        ("code_unique", "UNIQUE(code)", "A pairing code is unique."),
    ]
