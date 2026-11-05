# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import fields, models


class ResUsersSettings(models.Model):
    """Sounds and notifications of LinkUp, set by each member.

    Discuss lets a user write their own settings
    (``set_res_users_settings``) and sends them to the web client with the
    others, so these fields reach the Store as ``store.settings``. The
    reward sounds are off by default; the sound is never the only signal of
    an event.
    """

    _inherit = "res.users.settings"

    linkup_sound_enabled = fields.Boolean(
        string="LinkUp sounds",
        default=True,
        help="Sounds of a reflection sent and received.",
    )
    linkup_reward_sounds_enabled = fields.Boolean(
        string="LinkUp reward sounds",
        default=False,
        help="Sound of a confirmed reflection.",
    )
    linkup_notify_reflet_received = fields.Boolean(
        string="Notify a received reflection", default=True
    )
    linkup_notify_confirmed = fields.Boolean(
        string="Notify a confirmed reflection", default=True
    )
    linkup_notify_highlight = fields.Boolean(
        string="Notify a highlight", default=True
    )
    # Off by default on the web; the mobile application turns it on for
    # its own notifications (LU-F-092 RM4).
    linkup_notify_discreet = fields.Boolean(
        string="Discreet notifications",
        default=False,
        help="The notifications of LinkUp read “New LinkUp event”, without"
        " any name.",
    )
