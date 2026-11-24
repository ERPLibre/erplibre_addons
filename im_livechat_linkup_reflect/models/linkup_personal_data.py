# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""The retention of what LinkUp keeps of the conversations of its live
chat (LU-NF-015, Q-31): the periods of the members apply to the visitors.

The retention of ``mail_linkup_community`` already reaches the visitors
where it searches whatever the parties: a draft of a visitor unchanged for
``linkup.retention_draft_days`` days (30) is deleted, and a reflection of
the live chat rejected or expired for
``linkup.retention_closed_reflet_months`` months (12) loses its texts. An
event of points held for a visitor leaves after
``linkup.guest_event_expiry_days`` days (30, Q-43). This module adds the
conversations of the live chat channels of LinkUp, which no link of a pair
holds: ``_cron_linkup_livechat_retention`` deletes those without a message
for ``linkup.retention_inactive_pair_months`` months (24), the period of an
inactive pair, with their messages and their reflections. A conversation a
report points to stays while the report is open, then for
``linkup.retention_closed_report_months`` months (24) after its decision,
the period of a closed report: the evidence of the moderation outlives the
conversation by no more than its report. The live chat sessions outside
LinkUp keep the retention of ``im_livechat``.
"""

from odoo import api, models
from odoo.addons.mail_linkup_community.models.linkup_report import (
    CLOSED_STATES,
)
from odoo.tools import SQL


class LinkupPersonalData(models.AbstractModel):
    _inherit = "linkup.personal.data"

    @api.model
    def _cron_linkup_livechat_retention(self):
        """Delete the conversations of the live chat of LinkUp without a
        message for the period of an inactive pair, unless a report holds
        them, with their messages and their reflections. Return the
        conversations deleted."""
        conversations = self._linkup_inactive_livechat_conversations()
        conversations -= self._linkup_livechat_held(conversations)
        if conversations:
            self.env["linkup.reflet"].sudo().search(
                [("channel_id", "in", conversations.ids)]
            ).unlink()
            conversations.unlink()
        return conversations

    @api.model
    def _linkup_inactive_livechat_conversations(self):
        """The conversations of the live chat channels of LinkUp whose
        last message, or their creation without one, is older than the
        period of an inactive pair, under ``sudo``."""
        cutoff = self._linkup_cutoff("inactive_pair")
        self.env["discuss.channel"].flush_model(
            ["channel_type", "livechat_channel_id"]
        )
        self.env["mail.message"].flush_model(["model", "res_id", "date"])
        self.env.cr.execute(
            SQL(
                """
                SELECT channel.id
                FROM discuss_channel channel
                JOIN im_livechat_channel livechat
                  ON livechat.id = channel.livechat_channel_id
                WHERE channel.channel_type = 'livechat'
                  AND livechat.linkup_kind IS NOT NULL
                  AND COALESCE(
                      (SELECT MAX(message.date)
                       FROM mail_message message
                       WHERE message.model = 'discuss.channel'
                         AND message.res_id = channel.id),
                      channel.create_date
                  ) < %s
                """,
                cutoff,
            )
        )
        return (
            self.env["discuss.channel"]
            .sudo()
            .browse([row[0] for row in self.env.cr.fetchall()])
        )

    @api.model
    def _linkup_livechat_held(self, conversations):
        """The conversations of ``conversations`` a report holds: one
        still open, or closed for less than the period of a closed report,
        that comes from the conversation, opened it as a conversation of
        distress, or points to one of its messages or reflections."""
        if not conversations:
            return conversations
        ids = conversations.ids
        reports = (
            self.env["linkup.report"]
            .sudo()
            .search(
                [
                    "|",
                    "|",
                    "|",
                    ("livechat_conversation_id", "in", ids),
                    ("distress_channel_id", "in", ids),
                    ("reflet_id.channel_id", "in", ids),
                    "&",
                    ("message_id.model", "=", "discuss.channel"),
                    ("message_id.res_id", "in", ids),
                ]
            )
        )
        cutoff = self._linkup_cutoff("closed_report")
        holding = reports.filtered(
            lambda report: report.state not in CLOSED_STATES
            or (report.decision_date or report.write_date) >= cutoff
        )
        held_ids = set(
            holding.livechat_conversation_id.ids
            + holding.distress_channel_id.ids
            + holding.reflet_id.channel_id.ids
            + [
                message.res_id
                for message in holding.message_id
                if message.model == "discuss.channel"
            ]
        )
        return conversations.filtered(lambda channel: channel.id in held_ids)
