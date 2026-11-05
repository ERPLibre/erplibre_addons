# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import _, api, models
from odoo.exceptions import AccessError


class MailNotification(models.Model):
    _inherit = "mail.notification"

    @api.model_create_multi
    def create(self, vals_list):
        """Keep a restricted member from notifying anybody by the ORM.

        ``mail`` lets an internal user create the inbox notification of any
        message they read for any partner: the message would then reach a
        person past the start rule, a block and the scope of the member.
        The notifications of a post are created by the server under
        ``sudo``; outside it, a restricted member creates none.
        """
        if not self.env.su and self.env.user._linkup_is_restricted_member():
            raise AccessError(
                _("A LinkUp member notifies nobody outside a conversation.")
            )
        return super().create(vals_list)
