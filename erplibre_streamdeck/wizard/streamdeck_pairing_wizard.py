# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import _, api, fields, models


class StreamdeckPairingWizard(models.TransientModel):
    """Shows a new pairing code of the current user.

    Each wizard draws its own code from `streamdeck.service` at creation,
    in the name of the user who creates it: a code or an expiry given in
    the values is ignored. The code is a credential until it expires, so
    a global record rule lets only the wizard's creator read it; the
    pairing code records themselves stay closed to everyone.
    """

    _name = "streamdeck.pairing.wizard"
    _description = "Add a Stream Deck workstation"

    code = fields.Char(string="Pairing code", readonly=True)
    expires_at = fields.Datetime(string="Valid until", readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        Service = self.env["streamdeck.service"]
        values = []
        for vals in vals_list:
            code = Service.new_pairing_code(self.env.user)
            values.append(
                dict(vals, code=code.code, expires_at=code.expires_at)
            )
        return super().create(values)

    @api.model
    def action_open(self):
        """A window action showing a new wizard, hence a new code."""
        return {
            "type": "ir.actions.act_window",
            "name": _("Add a workstation"),
            "res_model": self._name,
            "res_id": self.create({}).id,
            "views": [(False, "form")],
            "target": "new",
        }
