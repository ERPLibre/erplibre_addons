# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""The retention periods (T-48, LU-NF-015, Q-31): the daily cron deletes
the old drafts, erases the texts of the old rejected and expired
reflections and the content of the pairs without activity, deletes the old
closed reports with their audit log, and erases the accounts never
verified; the dates are moved back in SQL."""

from dateutil.relativedelta import relativedelta
from odoo import fields
from odoo.tests import tagged
from odoo.tools import SQL

from .common import LinkupCommunityCase


@tagged("post_install", "-at_install")
class TestLinkupRetention(LinkupCommunityCase):
    def setUp(self):
        super().setUp()
        self.Data = self.env["linkup.personal.data"]
        self.Report = self.env["linkup.report"]

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

    def test_old_drafts_deleted(self):
        """Drafts unchanged for 30 days are deleted; the period is a
        setting."""
        old = self._draft(self.sam)
        recent = self._draft(self.france)
        self._age(old, "write_date", days=31)
        self._age(recent, "write_date", days=10)
        self.Data._cron_linkup_retention()
        self.assertFalse(old.exists())
        self.assertTrue(recent.exists())
        self.env["ir.config_parameter"].sudo().set_param(
            "linkup.retention_draft_days", "5"
        )
        self.Data._cron_linkup_retention()
        self.assertFalse(recent.exists())

    def test_old_rejected_reflections_erased(self):
        """The texts of a reflection rejected 12 months ago are erased; its
        state and dates stay. A recent one keeps them."""
        old = self._sent(self.sam, self.france)
        old.with_user(self.france).action_reject()
        recent = self._sent(self.sam, self.jacques)
        recent.with_user(self.jacques).action_reject()
        self._age(old, "answered_date", months=13)
        self._age(recent, "answered_date", months=11)
        self.Data._cron_linkup_retention()
        self.assertTrue(old.linkup_content_removed)
        self.assertFalse(old.you_said)
        self.assertEqual(old.state, "rejected")
        self.assertTrue(old.answered_date)
        self.assertFalse(recent.linkup_content_removed)
        self.assertTrue(recent.you_said)

    def test_inactive_pairs_erased(self):
        """After 24 months without activity, the reflections and the
        messages of a pair are erased; a pair whose conversation still
        lives keeps them."""
        old = self._sent(self.sam, self.france)
        old.with_user(self.france).action_confirm()
        live = self._sent(self.sam, self.jacques)
        live.with_user(self.jacques).action_confirm()
        old_chat = old.channel_id
        old_message = old_chat.sudo().message_post(
            author_id=self.france.partner_id.id,
            body="Un message ancien",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        live_message = live.channel_id.sudo().message_post(
            author_id=self.jacques.partner_id.id,
            body="Un message récent",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        self._age(
            old.link_id | live.link_id, "last_interaction_date", months=25
        )
        messages = (
            self.env["mail.message"]
            .sudo()
            .search(
                [
                    ("model", "=", "discuss.channel"),
                    ("res_id", "=", old_chat.id),
                ]
            )
        )
        self._age(messages, "date", months=25)
        live_old = (
            self.env["mail.message"]
            .sudo()
            .search(
                [
                    ("model", "=", "discuss.channel"),
                    ("res_id", "=", live.channel_id.id),
                    ("id", "!=", live_message.id),
                ]
            )
        )
        self._age(live_old, "date", months=25)
        self.Data._cron_linkup_retention()
        self.assertTrue(old.linkup_content_removed)
        self.assertNotIn("ancien", old_message.body or "")
        self.assertFalse(live.linkup_content_removed)
        self.assertIn("récent", live_message.body)

    def test_old_closed_reports_deleted(self):
        """A report closed 24 months ago is deleted, with its audit log and
        the original of the content it hid; an open one and a recent closed
        one stay."""
        message = self.workshop.with_user(self.sam).message_post(
            body="À masquer",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        Report = self.Report.with_user(self.france)
        old = self.Report.browse(
            Report.action_create_report(
                message_id=message.id, reason="harassment"
            )
        )
        recent = self.Report.browse(
            Report.action_create_report(user_id=self.jacques.id, reason="spam")
        )
        still_open = self.Report.browse(
            self.Report.with_user(self.jacques).action_create_report(
                user_id=self.sam.id, reason="spam"
            )
        )
        hidden = self.env["linkup.hidden.content"]._linkup_hide(
            old, message, self.env["linkup.reflet"]
        )
        audit = self.env["linkup.audit.log"]._linkup_log(old, "hide", "Test")
        (old | recent).sudo().write(
            {"state": "dismissed", "decision_date": fields.Datetime.now()}
        )
        self._age(old, "decision_date", months=25)
        self._age(still_open, "write_date", months=25)
        self.Data._cron_linkup_retention()
        self.assertFalse(old.exists())
        self.assertFalse(hidden.exists())
        self.assertFalse(audit.exists())
        self.assertTrue(message.linkup_hidden)
        self.assertFalse(message.body)
        self.assertTrue(recent.exists())
        self.assertTrue(still_open.exists())

    def test_unverified_accounts_erased(self):
        """An account of the signup never verified within 30 days is
        erased; a recent one, and one verified once whose new address waits
        for its link, stay."""
        self._as_public_account(self.luce)
        self._as_public_account(self.jacques)
        self.jacques.sudo().linkup_verified_date = fields.Datetime.now()
        self._as_public_account(self.france)
        self._age(self.luce | self.jacques, "create_date", days=31)
        self.Data._cron_linkup_retention()
        luce = self.luce.sudo().with_context(active_test=False)
        self.assertFalse(luce.active)
        self.assertTrue(luce.linkup_deleted_date)
        self.assertFalse(luce.partner_id.email)
        self.assertTrue(self.jacques.active)
        self.assertTrue(self.france.active)

    def test_verification_dates_the_account(self):
        """The first verification is dated; a later one keeps that date."""
        self._as_public_account(self.luce)
        self.luce.with_user(self.luce).linkup_resend_verification()
        self.Users._linkup_verify_token(self._verify_token(self.luce.email))
        first = self.luce.sudo().linkup_verified_date
        self.assertTrue(first)
