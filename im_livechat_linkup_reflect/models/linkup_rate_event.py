# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import fields, models


class LinkupRateEvent(models.Model):
    _inherit = "linkup.rate.event"

    kind = fields.Selection(
        selection_add=[
            ("livechat_session", "Live chat session"),
            ("livechat_help_now", "Need help now"),
        ],
        ondelete={
            "livechat_session": "cascade",
            "livechat_help_now": "cascade",
        },
    )
