# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import models


class GamificationBadgeUser(models.Model):
    _inherit = "gamification.badge.user"

    def _send_badge(self):
        """Announce the badge of a restricted member on the bus only.

        The native method mails the template ``email_template_badge_received``;
        a member receives no email of the gamification (LU-F-102 RM2,
        LU-NF-033). Other users keep the native email.
        """
        members = self.filtered(
            lambda badge_user: badge_user.user_id._linkup_is_restricted_member()
        )
        for badge_user in members:
            user = badge_user.user_id
            badge = badge_user.badge_id.with_context(lang=user.lang)
            user.partner_id._bus_send(
                "linkup.points/badge",
                {"badge_id": badge.id, "name": badge.name},
            )
        others = self - members
        if others:
            return super(GamificationBadgeUser, others)._send_badge()
        return True
