# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import _, fields, models
from odoo.exceptions import AccessError

from ..models.res_config_settings import FIRST_PILOT_POLICIES, PARAM_PREFIX

MANAGER_GROUP = "erplibre_streamdeck.group_streamdeck_manager"


class StreamdeckConfigPolicy(models.TransientModel):
    """The first-pilot policy of the organisation, as the Stream Deck
    manager forces it (Stream Deck › Configuration › First pilot).

    It writes the same `ir.config_parameter` as the field
    `streamdeck_first_pilot_policy` of Settings › Stream Deck, which only
    a Settings administrator reaches. Its access rights are the manager's
    only, and `action_save` checks the group again before writing the
    parameter as superuser: a record created by a manager does not let
    another user save it. A new form opens on the policy in place.
    """

    _name = "streamdeck.config.policy"
    _description = "First pilot policy"

    first_pilot_policy = fields.Selection(
        FIRST_PILOT_POLICIES,
        string="First pilot",
        required=True,
        default=lambda self: self.env[
            "streamdeck.config.schema"
        ]._first_pilot_policy(),
        help=(
            "At the first report of a piloted workstation, the free"
            " settings whose local value differs from Odoo's: the"
            " employee chooses, or this choice applies. Locked settings"
            " are always offered for the employee's confirmation."
        ),
    )

    def action_save(self):
        """Store the policy and close the form. Raises AccessError for a
        user who is not a Stream Deck manager."""
        self.ensure_one()
        if not self.env.user.has_group(MANAGER_GROUP):
            raise AccessError(
                _("Only a Stream Deck manager sets the first-pilot policy.")
            )
        self.env["ir.config_parameter"].sudo().set_param(
            PARAM_PREFIX + "first_pilot_policy", self.first_pilot_policy
        )
        return {"type": "ir.actions.act_window_close"}
