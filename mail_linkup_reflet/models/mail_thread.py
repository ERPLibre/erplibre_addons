# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import models

from . import privacy


class MailThread(models.AbstractModel):
    _inherit = "mail.thread"

    def _message_add_suggested_recipient(
        self, result, partner=None, email=None, lang=None, reason=""
    ):
        """Leave out of the recipients suggested to a restricted member the
        address of every one but their own (LU-NF-009, LU-F-112 RM3).

        ``/mail/thread/data`` sends them for any document the member reads,
        the partner of another member included, which suggests itself;
        ``mail`` writes the address from the partner read under ``sudo``.
        Every suggestion passes here, those that a model adds after the
        others included. A recipient without its address stays a partner
        the composer names, and ``mail`` keeps skipping it by its partner.
        A suggestion without a partner holds an address in each of its
        values, its name included, and is dropped: a later suggestion of
        the same address resolves to the same absence, and none repeats.
        """
        result = super()._message_add_suggested_recipient(
            result, partner=partner, email=email, lang=lang, reason=reason
        )
        if not privacy.contact_closed(self.env):
            return result
        own = self.env.user.partner_id.id
        result[:] = [
            recipient for recipient in result if recipient.get("partner_id")
        ]
        for recipient in result:
            if recipient["partner_id"] != own:
                recipient.pop("email", None)
        return result
