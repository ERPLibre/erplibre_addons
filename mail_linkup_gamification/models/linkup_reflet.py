# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from datetime import timedelta

from odoo import api, fields, models

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
    def _linkup_demo_points(self, user_ids, reflet_events, call_link_ids):
        """Pay the points of the demonstration through the scoring events.

        ``user_ids`` are the accounts of the demonstration: their creation
        is dated back to the day before their first link, so they are old
        enough to earn points, as members of three weeks are. Then each
        ``(reflet_id, code)`` of ``reflet_events`` reports ``code`` on that
        reflection for its two parties, as its action does, and each link
        of ``call_link_ids`` reports one answered call of its pair. The
        rules, their caps and the ledger apply as for any event, so the
        karma of each member equals the sum of their lines.
        """
        users = self.env["res.users"].sudo().browse(user_ids)
        first_link = (
            self.env["linkup.link"]
            .sudo()
            .search(
                [
                    "|",
                    ("user_a_id", "in", users.ids),
                    ("user_b_id", "in", users.ids),
                    ("first_link_date", "!=", False),
                ],
                order="first_link_date",
                limit=1,
            )
        )
        created = (first_link.first_link_date or fields.Datetime.now()) - (
            timedelta(days=1)
        )
        users.flush_recordset()
        self.env.cr.execute(
            "UPDATE res_users SET create_date = %s"
            " WHERE id IN %s AND create_date > %s",
            [created, tuple(users.ids) or (0,), created],
        )
        users.invalidate_recordset(["create_date"])
        for reflet_id, code in reflet_events:
            reflet = self.sudo().browse(reflet_id)
            reflet._linkup_event(
                code, reflet._linkup_parties(), link=reflet.link_id
            )
        for link in self.env["linkup.link"].sudo().browse(call_link_ids):
            self.browse()._linkup_event(
                CALL_CODE,
                link.user_a_id | link.user_b_id,
                link=link,
                key=f"demo:call:{link.id}",
            )
        return True

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
