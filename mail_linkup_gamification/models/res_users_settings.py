# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import fields, models


class ResUsersSettings(models.Model):
    """The setting of a member that takes the points out of their screens.

    It lives with the sounds and notifications of the core, which Discuss
    lets a user write and sends to the web client as ``store.settings``.
    The points are still counted: only their display and their animations
    are hidden (LU-F-091 RM2).
    """

    _inherit = "res.users.settings"

    linkup_hide_gamification = fields.Boolean(
        string="Hide the points and their animations",
        default=False,
        help="The energy, the “+N” of the points, their sound and the"
        " ranks and badges no longer show on the LinkUp screens.",
    )
