# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import fields, models


class DiscussChannelRtcSession(models.Model):
    _inherit = "discuss.channel.rtc.session"

    # Written by the server only: ``_update_and_broadcast``, the single
    # write a client reaches, keeps the fields of the media state.
    linkup_call_answered = fields.Boolean(
        string="Answered call",
        readonly=True,
        copy=False,
        help="The call this session belongs to was answered: a participant"
        " who joins it again does not answer it a second time.",
    )
