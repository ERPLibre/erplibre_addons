# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models

# The display levels of the studio editor: « simple » shows the view as a
# user sees it, « detailed » adds the technical names, the xml ids and the
# xpaths.
DISPLAY_LEVELS = [("simple", "Simple"), ("detailed", "Detailed")]


class ResUsersSettings(models.Model):
    """The display level of the studio editor, one per user account. The
    base rule on res.users.settings lets each user read and write his own
    row."""

    _inherit = "res.users.settings"

    erplibre_studio_display_level = fields.Selection(
        DISPLAY_LEVELS,
        string="Studio display level",
        default="simple",
        required=True,
    )
