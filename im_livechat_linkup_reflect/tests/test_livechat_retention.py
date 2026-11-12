# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""The retention periods applied to the visitors of the live chat
(LU-NF-015, Q-31): the draft of a visitor, the texts of a reflection of
the live chat rejected long ago, and the conversations of LinkUp without a
message for the period of an inactive pair, which a report keeps until its
own period is over. The dates are moved back in SQL."""

from dateutil.relativedelta import relativedelta
from odoo import fields
from odoo.tests import tagged
from odoo.tools import SQL

from .common import LinkupLivechatCase
from .test_livechat_reflet import DRAFT, LinkupLivechatRefletMixin


@tagged("post_install", "-at_install")
class TestLinkupLivechatRetention(
    LinkupLivechatRefletMixin, LinkupLivechatCase
):
    def setUp(self):
        super().setUp()
        self.Data = self.env["linkup.personal.data"]
        self.Reflet = self.env["linkup.reflet"]

    def _age(self, records, column, **delta):
        """Move ``column`` of ``records`` back by ``delta`` from now."""
        records.flush_recordset()
        self.env.cr.execute(
            SQL(
                "UPDATE %s SET %s = %s WHERE id IN %s",
                SQL.identifier(records._table),
                SQL.identifier(column),
                fields.Datetime.now() - relativedelta(**delta),
                tuple(records.ids),
            )
        )
        records.invalidate_recordset()

    def _age_conversation(self, channel, **delta):
        """Move the creation and every message of ``channel`` back by
        ``delta``."""
        channel = channel.sudo()
        self._age(channel, "create_date", **delta)
        self._age(channel.message_ids, "date", **delta)

    def _close(self, report, **delta):
        """Close ``report``, its decision moved back by ``delta``."""
        report.flush_recordset()
        self.env.cr.execute(
            "UPDATE linkup_report SET state = 'dismissed', decision_date = %s"
            " WHERE id = %s",
            [fields.Datetime.now() - relativedelta(**delta), report.id],
        )
        report.invalidate_recordset()

    def _set(self, key, value):
        self.env["ir.config_parameter"].sudo().set_param(key, value)

    def test_draft_of_a_visitor_deleted(self):
        """The draft of a visitor unchanged for 30 days is deleted by the
        retention of the members; a recent one stays."""
        channel, guest = self._welcome_session()
        draft = self.Reflet.sudo().browse(
            self.Reflet._linkup_livechat_save_draft(
                channel.id, dict(DRAFT, category_id=self.goals.id), guest=guest
            )
        )
        _other_channel, other = self._welcome_session()
        recent = self.Reflet.sudo().browse(
            self.Reflet._linkup_guest_save_draft(other, DRAFT)
        )
        self._age(draft, "write_date", days=31)
        self.Data._cron_linkup_retention()
        self.assertFalse(draft.exists())
        self.assertTrue(recent.exists())

    def test_rejected_reflection_of_a_visitor_erased(self):
        """The texts of a reflection of the live chat rejected 12 months
        ago are erased; its state stays."""
        channel, guest = self._member_session()
        reflet = self._visitor_reflet(channel, guest)
        reflet.with_user(self.nicolas)._linkup_livechat_answer("rejected")
        self._age(reflet, "answered_date", months=13)
        self.Data._cron_linkup_retention()
        self.assertTrue(reflet.linkup_content_removed)
        self.assertFalse(reflet.you_said)
        self.assertEqual(reflet.state, "rejected")

    def test_inactive_conversation_deleted(self):
        """A conversation of the welcome channel without a message for 24
        months is deleted, with its messages and its reflections; a
        conversation that still lives stays. The period is a setting."""
        old, guest = self._member_session()
        reflet = self._visitor_reflet(old, guest)
        messages = old.sudo().message_ids
        self.assertTrue(messages)
        live, _guest = self._welcome_session()
        self._age_conversation(old, months=25)
        self._age_conversation(live, months=23)
        deleted = self.Data._cron_linkup_livechat_retention()
        self.assertEqual(deleted, old)
        self.assertFalse(old.exists())
        self.assertFalse(messages.exists())
        self.assertFalse(reflet.exists())
        self.assertTrue(live.exists())
        self._set("linkup.retention_inactive_pair_months", "12")
        self.Data._cron_linkup_livechat_retention()
        self.assertFalse(live.exists())

    def test_period_below_one_takes_the_default(self):
        """A period of 0 falls back to 24 months: nothing younger
        leaves."""
        channel, _guest = self._welcome_session()
        self._age_conversation(channel, months=13)
        self._set("linkup.retention_inactive_pair_months", "0")
        self.Data._cron_linkup_livechat_retention()
        self.assertTrue(channel.exists())

    def test_distress_conversation_kept_by_its_report(self):
        """A conversation of distress stays while its report is open,
        however old, then for 24 months after the decision; past that
        period it is deleted."""
        self._online(self.jean)
        channel, guest = self._welcome_session()
        self._chatbot(
            channel,
            "Need help now",
            answer=self._answer("welcome_answer_help"),
            guest=guest,
        )
        self.assertEqual(channel.livechat_channel_id, self.distress)
        report = (
            self.env["linkup.report"]
            .sudo()
            .search([("distress_channel_id", "=", channel.id)])
        )
        self.assertTrue(report)
        self._age_conversation(channel, months=30)
        self.Data._cron_linkup_livechat_retention()
        self.assertTrue(channel.exists())
        self._close(report, months=23)
        self.Data._cron_linkup_livechat_retention()
        self.assertTrue(channel.exists())
        self._close(report, months=25)
        self.Data._cron_linkup_livechat_retention()
        self.assertFalse(channel.exists())

    def test_conversation_of_a_reported_visitor_kept(self):
        """The conversation of a visitor whom its operator reported stays
        while the report is open."""
        channel, _guest = self._member_session()
        self.env["linkup.report"].with_user(
            self.nicolas
        ).action_report_livechat_visitor(channel.id, reason="spam")
        self._age_conversation(channel, months=25)
        self.Data._cron_linkup_livechat_retention()
        self.assertTrue(channel.exists())

    def test_cron_record(self):
        """The data holds the daily cron of the retention of the live
        chat."""
        cron = self.env.ref(
            "im_livechat_linkup_reflect.ir_cron_linkup_livechat_retention"
        )
        self.assertEqual(cron.interval_type, "days")
        self.assertTrue(cron.active)
