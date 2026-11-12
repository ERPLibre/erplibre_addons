# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Consents (T-39, LU-F-111, LU-NF-013, LU-NF-050): recorded by the server
only, versioned and dated, withdrawn at once, required to send."""

from odoo import fields
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.addons.mail_linkup_reflet.tests.common import MEMBER
from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import LinkupCommunityCase

REQUIRED = ("terms", "privacy", "sensitive_data")


@tagged("post_install", "-at_install")
class TestLinkupConsent(LinkupCommunityCase):
    def test_member_writes_no_consent(self):
        """CA3: neither create, write nor unlink by RPC; the actions
        record a row for the current user only."""
        Consent = self.Consent.with_user(self.sam)
        with self.assertRaises(AccessError):
            Consent.create(
                {
                    "user_id": self.sam.id,
                    "purpose": "sensitive_data",
                    "granted": True,
                    "version": "1",
                }
            )
        Consent.action_grant(["sensitive_data"])
        row = Consent.search([("purpose", "=", "sensitive_data")])
        self.assertEqual(row.user_id, self.sam)
        with self.assertRaises(AccessError):
            row.write({"granted": False})
        with self.assertRaises(AccessError):
            row.unlink()
        self.assertFalse(
            self.Consent.with_user(self.france).search(
                [("user_id", "=", self.sam.id)]
            )
        )

    def test_grant_then_revoke_is_proven(self):
        """RM1, RM3: each decision is a row with its version and date; the
        latest one decides; the terms are not withdrawn."""
        self.env["ir.config_parameter"].sudo().set_param(
            "linkup.consent_version.sensitive_data", "2026-1"
        )
        Consent = self.Consent.with_user(self.sam)
        Consent.action_grant("sensitive_data")
        Consent.action_revoke(["sensitive_data"])
        rows = self.Consent.search(
            [("user_id", "=", self.sam.id), ("purpose", "=", "sensitive_data")]
        )
        self.assertEqual(rows.mapped("granted"), [False, True])
        self.assertEqual(set(rows.mapped("version")), {"2026-1"})
        self.assertTrue(all(row.date <= fields.Datetime.now() for row in rows))
        self.assertFalse(
            self.Consent._linkup_active(self.sam, "sensitive_data")
        )
        info = {row["purpose"]: row for row in Consent.linkup_consents_info()}
        self.assertFalse(info["sensitive_data"]["granted"])
        self.assertTrue(info["sensitive_data"]["revocable"])
        self.assertFalse(info["terms"]["revocable"])
        for purpose in ("terms", "privacy", "unknown"):
            with self.subTest(purpose=purpose):
                with self.assertLinkupCode("linkup.validation", "purpose"):
                    Consent.action_revoke([purpose])

    def test_sensitive_data_required_to_send(self):
        """CA2, LU-NF-050: without an active consent to sensitive
        information, ``action_send`` is refused; withdrawing it stops the
        sending at once."""
        self._as_public_account(
            self.sam, verified=True, consents=("terms", "privacy")
        )
        draft = self._draft()
        with self.assertLinkupCode("linkup.consent_required"):
            draft.with_user(self.sam).action_send(self.france.id)
        self.assertEqual(
            self.Users.browse(self.sam.id)._linkup_consent_state()[
                "linkup_consent_missing"
            ],
            ["sensitive_data"],
        )
        self.Consent.with_user(self.sam).action_grant(["sensitive_data"])
        draft.with_user(self.sam).action_send(self.france.id)
        self.assertEqual(draft.state, "sent")
        self.Consent.with_user(self.sam).action_revoke(["sensitive_data"])
        other = self._draft()
        with self.assertLinkupCode("linkup.consent_required"):
            other.with_user(self.sam).action_send(self.france.id)
        with self.assertLinkupCode("linkup.consent_required"):
            other.with_user(self.sam).action_send(
                invite={"email": "camille.nouvelle@example.com"}
            )

    def test_answers_need_the_consents_too(self):
        """An answer is an exchange: the recipient without the consents
        confirms nothing, but reads."""
        reflet = self._sent()
        self._as_public_account(self.france, verified=True)
        reflet.with_user(self.france).action_mark_read()
        with self.assertLinkupCode("linkup.consent_required"):
            reflet.with_user(self.france).action_confirm()

    def test_consents_of_every_member(self):
        """The setting extends the required consents to the members an
        administrator created."""
        draft = self._draft()
        self.env["ir.config_parameter"].sudo().set_param(
            "linkup.consent_all_members", "True"
        )
        with self.assertLinkupCode("linkup.consent_required"):
            draft.with_user(self.sam).action_send(self.france.id)
        self.Consent.with_user(self.sam).action_grant(list(REQUIRED))
        draft.with_user(self.sam).action_send(self.france.id)
        self.assertEqual(draft.state, "sent")

    def test_notifications_consent_drives_the_settings(self):
        """Withdrawing the consent to notifications turns the notifications
        of LinkUp off; granting it turns them on."""
        Settings = self.env["res.users.settings"].sudo()
        settings = Settings._find_or_create_for_user(self.sam)
        self.Consent.with_user(self.sam).action_revoke(["notifications"])
        self.assertFalse(settings.linkup_notify_reflet_received)
        self.assertFalse(settings.linkup_notify_invitation_accepted)
        self.Consent.with_user(self.sam).action_grant(["notifications"])
        self.assertTrue(settings.linkup_notify_confirmed)

    def test_visibility_follows_the_module_that_brings_it(self):
        """A visibility consent applies only with the module of its field;
        without it, it cannot be changed."""
        available = "linkup_links_visible" in self.Users._fields
        self.assertEqual(
            self.Consent._linkup_available("link_visibility"), available
        )
        purposes = [
            row["purpose"]
            for row in self.Consent.with_user(self.sam).linkup_consents_info()
        ]
        self.assertEqual("link_visibility" in purposes, available)
        if not available:
            with self.assertLinkupCode("linkup.validation", "purpose"):
                self.Consent.with_user(self.sam).action_grant(
                    ["link_visibility"]
                )

    def test_network_preferences_record_consents(self):
        """§9.3: writing a visibility preference of the Network view, as
        its client does, records the consent; granting the consent writes
        the preference."""
        if "linkup_links_visible" not in self.Users._fields:
            self.skipTest("mail_linkup_network is not installed")
        self.sam.with_user(self.sam).write({"linkup_links_visible": True})
        self.assertTrue(
            self.Consent._linkup_active(self.sam, "link_visibility")
        )
        self.Consent.with_user(self.sam).action_revoke(["link_visibility"])
        self.assertFalse(self.sam.sudo().linkup_links_visible)
        self.Consent.with_user(self.sam).action_grant(["energy_visibility"])
        self.assertTrue(self.sam.sudo().linkup_energy_visible)

    def test_visibility_given_at_creation_is_recorded(self):
        """LU-NF-013: an account created with its links visible holds the
        proof of that consent; a preference left unset records none."""
        if "linkup_links_visible" not in self.Users._fields:
            self.skipTest("mail_linkup_network is not installed")
        joanna = mail_new_test_user(
            self.env,
            login="linkup_cs_joanna",
            name="Joanna",
            email="linkup_cs_joanna@example.com",
            groups=MEMBER,
            linkup_links_visible=True,
        )
        self.assertTrue(self.Consent._linkup_active(joanna, "link_visibility"))
        self.assertFalse(
            self.Consent.sudo().search_count(
                [
                    ("user_id", "=", joanna.id),
                    ("purpose", "=", "energy_visibility"),
                ]
            )
        )

    def test_visibility_granted_before_the_module_is_recorded(self):
        """LU-NF-013: a visibility granted before this module, as the demo
        of the Network view grants it, gets its consent at the
        installation, once; a decision already recorded is kept."""
        if "linkup_links_visible" not in self.Users._fields:
            self.skipTest("mail_linkup_network is not installed")
        demo = self.env.ref(
            "mail_linkup_reflet.demo_user_france", raise_if_not_found=False
        )
        if demo and demo.sudo().linkup_links_visible:
            self.assertTrue(
                self.Consent._linkup_active(demo, "link_visibility")
            )
        self.france.sudo().write({"linkup_links_visible": True})
        self.jacques.sudo().write({"linkup_links_visible": False})
        self.Consent.sudo().search(
            [("user_id", "in", (self.france | self.jacques).ids)]
        ).unlink()
        self.france.action_archive()
        rows = self.Consent._linkup_record_granted_mirrors()
        self.assertEqual(
            [(row.user_id, row.purpose, row.granted) for row in rows],
            [(self.france, "link_visibility", True)],
        )
        self.assertFalse(self.Consent._linkup_record_granted_mirrors())
