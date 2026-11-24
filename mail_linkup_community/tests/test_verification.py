# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Verification of the address (T-19, LU-F-110 RM3, CA3): before the link,
no reflection, no invitation, no highlight; the link serves once within 24
hours; a new link waits ``linkup.verification_resend_minutes``."""

from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from .common import LinkupCommunityCase


@tagged("post_install", "-at_install")
class TestLinkupVerification(LinkupCommunityCase):
    def setUp(self):
        super().setUp()
        self._as_public_account(
            self.sam, consents=("terms", "privacy", "sensitive_data")
        )

    def test_nothing_before_the_link(self):
        """CA3: the sending, an invitation and a highlight are refused with
        ``linkup.not_verified``; after the link, the sending passes."""
        draft = self._draft()
        with self.assertLinkupCode("linkup.not_verified"):
            draft.with_user(self.sam).action_send(self.france.id)
        with self.assertLinkupCode("linkup.not_verified"):
            draft.with_user(self.sam).action_send(
                invite={"email": "camille.nouvelle@example.com"}
            )
        with self.assertLinkupCode("linkup.not_verified"):
            self.env["linkup.highlight"].with_user(self.sam).action_send(
                self.france.id
            )
        self.assertEqual(draft.state, "draft")
        self.sam.sudo()._linkup_send_verification()
        token = self._verify_token(self.sam.email)
        self.assertEqual(self.Users._linkup_verify_token(token), self.sam)
        draft.with_user(self.sam).action_send(self.france.id)
        self.assertEqual(draft.state, "sent")
        # The link served once.
        self.assertFalse(self.Users._linkup_verify_token(token))

    def test_link_expires(self):
        """The link lasts 24 hours."""
        self.sam.sudo()._linkup_send_verification()
        token = self._verify_token(self.sam.email)
        self.sam.sudo().linkup_verify_expiry = (
            fields.Datetime.now() - timedelta(minutes=1)
        )
        self.assertFalse(self.Users._linkup_verify_token(token))
        self.assertFalse(self.sam.sudo().linkup_email_verified)
        self.assertFalse(self.Users._linkup_verify_token("z" * 43))

    def test_resend_is_limited(self):
        """LU-NF-006: one new link per 10 minutes, then
        ``linkup.rate_limited``; the email is generic and holds the link."""
        result = self.Users.with_user(self.sam).linkup_resend_verification()
        self.assertEqual(result["email"], "l***@example.com")
        mail = self._mails_to(self.sam.email)
        self.assertEqual(len(mail), 1)
        self.assertIn("/linkup/verify/", mail.body_html)
        self.assertFalse(mail.model)
        with self.assertLinkupCode("linkup.rate_limited"):
            self.Users.with_user(self.sam).linkup_resend_verification()
        self.env["linkup.rate.event"].flush_model()
        self.env.cr.execute(
            "UPDATE linkup_rate_event"
            " SET create_date = create_date - interval '11 minutes'"
        )
        self.env["linkup.rate.event"].invalidate_model()
        self.Users.with_user(self.sam).linkup_resend_verification()
        self.assertEqual(len(self._mails_to(self.sam.email)), 2)

    def test_unverified_member_receives_no_invitation(self):
        """An invitation by code does not reach an unverified account."""
        code = self.sam.sudo()._linkup_code()
        reflet = self._draft(self.france)
        result = reflet.with_user(self.france).action_send(
            invite={"code": code}
        )
        invitation = self.Invitation.sudo().browse(result["id"])
        self.assertFalse(invitation.invitee_id)

    def test_new_address_is_verified_again(self):
        """LU-F-082: a new address from the profile needs its link."""
        self.sam.sudo().linkup_email_verified = True
        self.Users.with_user(self.sam).linkup_profile_write(
            {"email": "sam.nouveau@example.com"}
        )
        self.assertFalse(self.sam.sudo().linkup_email_verified)
        self.assertEqual(self.sam.email, "sam.nouveau@example.com")
        self.assertTrue(self._verify_token("sam.nouveau@example.com"))
