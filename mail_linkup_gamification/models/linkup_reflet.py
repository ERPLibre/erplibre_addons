# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import api, models

from .linkup_points_rule import CALL_CODE


class LinkupReflet(models.Model):
    _inherit = "linkup.reflet"

    def _linkup_event(self, code, users, link=None, channel=None, key=None):
        """Apply the point rules of a scoring event of the core.

        An answered call waits for its end when the LinkUp administrator
        sets a minimum duration (``linkup.points.call``). A confirmation
        also runs the collusion alerts of the moderation (§7.3).
        """
        res = super()._linkup_event(
            code, users, link=link, channel=channel, key=key
        )
        reflet = self.sudo()[:1]
        Call = self.env["linkup.points.call"].sudo()
        if code == CALL_CODE and Call._linkup_min_duration() > 0:
            Call._linkup_wait(code, link, reflet, channel, key)
        else:
            self.env["linkup.points.rule"]._linkup_apply_event(
                code, users, link=link, reflet=reflet, channel=channel, key=key
            )
        if code == "reflect_confirmed" and reflet:
            self.env["linkup.report"].sudo()._linkup_check_collusion(reflet)
        return res

    @api.model
    def linkup_channel_info(self, channel_id):
        """Add ``link_energy`` to what the web client shows of a direct
        conversation: the energy of the link of the pair as the member
        reads it, the points they received in its events (LU-F-071 RM2),
        0 without a link."""
        info = super().linkup_channel_info(channel_id)
        if info.get("available"):
            me = self.env.user
            peer = self._linkup_chat_peer(channel_id)
            link = self.env["linkup.link"]._get_between(me, peer)
            info["link_energy"] = link._linkup_energy_for(me) if link else 0
        return info
