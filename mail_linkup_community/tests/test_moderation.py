# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""The moderation of the community (T-16, T-37, T-49, LU-F-114, LU-F-116,
LU-F-118, LU-NF-040 to LU-NF-042): the rights on the reports and on the
audit log, the conflicts of interest, the decisions and their audit, the
appeal, and what the reported member never learns."""

from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.addons.mail.tools.discuss import Store
from odoo.exceptions import AccessError, UserError
from odoo.tests import HttpCase, tagged
from odoo.tools import mute_logger

from .common import LinkupCommunityCase

MODERATOR = "mail_linkup_reflet.group_linkup_moderator"
ADMIN = "mail_linkup_reflet.group_linkup_admin"


class LinkupModerationMixin:
    """Two moderators without a link (Joanna, Jean), a moderator linked to
    Sam (Thomas) and a LinkUp administrator (Henri), with the members of
    the reflections module."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        def user(login, name, group):
            return mail_new_test_user(
                cls.env,
                login=login,
                name=name,
                email=f"{login}@example.com",
                groups=group,
            )

        cls.joanna = user("linkup_md_joanna", "Joanna", MODERATOR)
        cls.jean = user("linkup_md_jean", "Jean", MODERATOR)
        cls.thomas = user("linkup_md_thomas", "Thomas", MODERATOR)
        cls.henri = user("linkup_md_henri", "Henri", ADMIN)
        cls.env["linkup.link"]._get_or_create(cls.thomas, cls.sam)
        cls.workshop.add_members(
            partner_ids=(
                cls.joanna | cls.jean | cls.thomas | cls.henri
            ).partner_id.ids
        )
        cls.Report = cls.env["linkup.report"]
        cls.Audit = cls.env["linkup.audit.log"]
        cls.Notice = cls.env["linkup.moderation.notice"]

    def _report(self, user, **kwargs):
        values = {"reason": "harassment"}
        values.update(kwargs)
        return self.Report.browse(
            self.Report.with_user(user).action_create_report(**values)
        )

    def _post(self, user, body, channel=None):
        channel = channel or self.workshop
        return channel.with_user(user).message_post(
            body=body, message_type="comment", subtype_xmlid="mail.mt_comment"
        )

    def _as(self, user):
        return self.Report.with_user(user)

    def _queue_ids(self, user, scope="open"):
        return [
            row["id"]
            for row in self._as(user).linkup_moderation_queue(scope)["rows"]
        ]

    def _decide(self, user, report, decision, reason="Breach", **kwargs):
        Report = self._as(user)
        Report.action_moderation_take(report.id)
        return Report.action_moderation_decide(
            report.id, decision, reason, **kwargs
        )


@tagged("post_install", "-at_install")
class TestLinkupModerationRights(LinkupModerationMixin, LinkupCommunityCase):
    @mute_logger("odoo.addons.base.models.ir_model", "odoo.models")
    def test_member_reads_their_own_reports_only(self):
        """A member reads the reports they made, never those about them nor
        those of others; the console refuses them (LU-NF-003)."""
        report = self._report(self.france, reflet_id=self._sent().id)
        self.assertEqual(self.Report.with_user(self.france).search([]), report)
        for member in (self.sam, self.jacques):
            self.assertFalse(self.Report.with_user(member).search([]))
            with self.assertRaises(AccessError):
                report.with_user(member).read(["reason"])
            with self.assertRaises(AccessError):
                self._as(member).linkup_moderation_queue()
            with self.assertRaises(AccessError):
                self._as(member).linkup_moderation_detail(report.id)
        rows = self.Report.with_user(self.france).linkup_my_reports()
        self.assertEqual(
            [(row["id"], row["progress"], row["member"]) for row in rows],
            [(report.id, "received", "Sam")],
        )
        self.assertNotIn("reporter", rows[0])
        self.assertFalse(self.Report.with_user(self.sam).linkup_my_reports())

    @mute_logger("odoo.addons.base.models.ir_model", "odoo.models")
    def test_conflicts_of_interest(self):
        """A moderator neither sees nor processes a report they made, one
        about them, or one whose parties share a link with them, through
        the console or the ORM (LU-F-116 RM5, CA3)."""
        about_sam = self._report(self.france, reflet_id=self._sent().id)
        by_joanna = self._report(self.joanna, user_id=self.sam.id)
        about_joanna = self._report(self.jacques, user_id=self.joanna.id)
        auto = self.Report.sudo().create(
            {
                "reported_user_id": self.jacques.id,
                "reason": "repeated_rejections",
                "auto_generated": True,
            }
        )
        self.assertEqual(
            set(self._queue_ids(self.joanna)), {about_sam.id, auto.id}
        )
        self.assertEqual(
            set(self.Report.with_user(self.joanna).search([]).ids),
            {about_sam.id, auto.id, by_joanna.id},
        )
        # Thomas is linked to Sam: no report of Sam is his to process.
        self.assertEqual(
            set(self._queue_ids(self.thomas)), {about_joanna.id, auto.id}
        )
        self.assertNotIn(
            about_sam, self.Report.with_user(self.thomas).search([])
        )
        with self.assertLinkupCode("linkup.unavailable"):
            self._as(self.thomas).linkup_moderation_detail(about_sam.id)
        with self.assertLinkupCode("linkup.unavailable"):
            self._as(self.thomas).action_moderation_take(about_sam.id)
        with self.assertLinkupCode("linkup.unavailable"):
            self._as(self.thomas).linkup_moderation_content(about_sam.id)
        with self.assertRaises(AccessError):
            about_sam.with_user(self.thomas).write({"state": "in_review"})
        # Her own report stays readable to Joanna as a member, not
        # processable.
        with self.assertRaises(AccessError):
            by_joanna.with_user(self.joanna).write({"state": "dismissed"})
        with self.assertLinkupCode("linkup.unavailable"):
            self._as(self.joanna).action_moderation_take(by_joanna.id)
        # The administrator manages the other reports, and neither reads
        # nor processes one in a conflict.
        self.assertIn(about_sam, self.Report.with_user(self.henri).search([]))
        self.Link._get_or_create(self.henri, self.france)
        self.assertNotIn(about_sam.id, self._queue_ids(self.henri))
        self.assertNotIn(
            about_sam, self.Report.with_user(self.henri).search([])
        )
        with self.assertRaises(AccessError):
            about_sam.with_user(self.henri).write({"state": "dismissed"})

    def test_moderator_without_report_reads_no_conversation(self):
        """A moderator reads no message of a conversation they are not in,
        whether a report exists or not (LU-F-116 CA2)."""
        reflet = self._sent()
        chat = reflet.channel_id
        self.assertTrue(chat)
        self.assertFalse(
            self.env["discuss.channel"]
            .with_user(self.joanna)
            .search([("id", "=", chat.id)])
        )
        domain = [("model", "=", "discuss.channel"), ("res_id", "=", chat.id)]
        Message = self.env["mail.message"].with_user(self.joanna)
        self.assertFalse(Message.search(domain))
        self._report(self.france, reflet_id=reflet.id)
        self.assertFalse(Message.search(domain))
        self.assertFalse(
            self.env["linkup.reflet"]
            .with_user(self.joanna)
            .search([("id", "=", reflet.id)])
        )


@tagged("post_install", "-at_install")
class TestLinkupModerationAudit(LinkupModerationMixin, LinkupCommunityCase):
    @mute_logger("odoo.addons.base.models.ir_model", "odoo.models")
    def test_audit_log_is_append_only(self):
        """Every reading of content and every decision adds a row; the
        moderators read them, the members do not, and nobody changes or
        deletes one (LU-NF-040)."""
        report = self._report(self.france, reflet_id=self._sent().id)
        detail = self._as(self.joanna).linkup_moderation_detail(report.id)
        self.assertFalse(detail["audit"])
        content = self._as(self.joanna).linkup_moderation_content(report.id)
        self.assertEqual(content["source"], "reflet")
        self.assertEqual(
            content["items"][0]["you_said"],
            "Que tu cherches du temps pour ton jardin.",
        )
        self._decide(self.joanna, report, "warn", "Insistance")
        rows = self.Audit.with_user(self.jean).search(
            [("report_id", "=", report.id)], order="id"
        )
        self.assertEqual(
            rows.mapped("action"), ["content_read", "take", "warn"]
        )
        self.assertEqual(rows.actor_id, self.joanna)
        self.assertEqual(rows[0].res_model, "linkup.reflet")
        self.assertEqual(rows[0].res_id, report.reflet_id.id)
        self.assertEqual(rows[2].reason, "Insistance")
        detail = self._as(self.jean).linkup_moderation_detail(report.id)
        self.assertEqual(
            [row["action"] for row in detail["audit"]],
            ["content_read", "take", "warn"],
        )
        # Thomas is linked to Sam: the audit of this report is not his.
        self.assertFalse(self.Audit.with_user(self.thomas).search([]))
        for member in (self.sam, self.france):
            with self.assertRaises(AccessError):
                self.Audit.with_user(member).search([])
        for user in (self.joanna, self.henri):
            with self.assertRaises(AccessError):
                rows.with_user(user).write({"reason": "Autre"})
            with self.assertRaises(AccessError):
                rows.with_user(user).unlink()
        with self.assertRaises(AccessError):
            rows.sudo().write({"reason": "Autre"})
        with self.assertRaises(AccessError):
            rows.sudo().unlink()
        with self.assertRaises(AccessError):
            self.Audit.with_user(self.henri).create(
                {
                    "actor_id": self.henri.id,
                    "action": "dismiss",
                    "report_id": report.id,
                }
            )

    def test_orm_change_of_processing_is_audited(self):
        """A moderator who changes a report through the ORM leaves a row."""
        report = self._report(self.france, user_id=self.sam.id)
        report.with_user(self.joanna).write({"state": "in_review"})
        row = self.Audit.sudo().search([("report_id", "=", report.id)])
        self.assertEqual(row.action, "update")
        self.assertEqual(row.actor_id, self.joanna)

    def test_context_of_a_message(self):
        """The console serves the reported message and the messages around
        it, as many as the setting says, and nothing else."""
        messages = [
            self._post(user, f"Message {index}")
            for index, user in enumerate(
                [self.sam, self.france, self.jacques] * 3
            )
        ]
        reported = messages[4]
        other = self.env["discuss.channel"].create(
            {
                "name": "Ailleurs",
                "channel_type": "group",
                "channel_partner_ids": [
                    (4, user.partner_id.id) for user in (self.sam, self.france)
                ],
            }
        )
        self._post(self.sam, "Ailleurs", channel=other)
        report = self._report(self.sam, message_id=reported.id)
        content = self._as(self.joanna).linkup_moderation_content(report.id)
        texts = [item["text"] for item in content["items"]]
        self.assertEqual(texts, [f"Message {index}" for index in range(1, 8)])
        self.assertEqual(
            [item["reported"] for item in content["items"]],
            [False, False, False, True, False, False, False],
        )
        self.env["ir.config_parameter"].sudo().set_param(
            "linkup.moderation_context_messages", "1"
        )
        content = self._as(self.joanna).linkup_moderation_content(report.id)
        self.assertEqual(
            [item["text"] for item in content["items"]],
            ["Message 3", "Message 4", "Message 5"],
        )
        self.assertEqual(
            self.Audit.sudo()
            .search([("report_id", "=", report.id)])
            .mapped("res_id"),
            [reported.id, reported.id],
        )

    def test_member_report_has_no_content(self):
        """A reported member comes with no content; the reading is
        written anyway."""
        report = self._report(self.france, user_id=self.jacques.id)
        content = self._as(self.joanna).linkup_moderation_content(report.id)
        self.assertEqual(content, {"source": "member", "items": []})
        row = self.Audit.sudo().search([("report_id", "=", report.id)])
        self.assertEqual(
            (row.res_model, row.res_id), ("res.users", self.jacques.id)
        )


@tagged("post_install", "-at_install")
class TestLinkupModerationDecisions(
    LinkupModerationMixin, LinkupCommunityCase
):
    def test_decide_needs_the_report_taken_and_a_reason(self):
        report = self._report(self.france, user_id=self.sam.id)
        Report = self._as(self.joanna)
        with self.assertLinkupCode("linkup.already_answered"):
            Report.action_moderation_decide(report.id, "warn", "Raison")
        Report.action_moderation_take(report.id)
        self.assertEqual(report.state, "in_review")
        self.assertEqual(report.moderator_id, self.joanna)
        with self.assertLinkupCode("linkup.already_answered"):
            self._as(self.jean).action_moderation_decide(
                report.id, "warn", "Raison"
            )
        with self.assertLinkupCode("linkup.validation", field="reason"):
            Report.action_moderation_decide(report.id, "warn", "  ")
        with self.assertLinkupCode("linkup.validation", field="decision"):
            Report.action_moderation_decide(report.id, "erase", "Raison")
        with self.assertLinkupCode("linkup.validation", field="days"):
            Report.action_moderation_decide(
                report.id, "suspend", "Raison", days=400
            )
        with self.assertLinkupCode("linkup.validation", field="decision"):
            Report.action_moderation_decide(report.id, "hide", "Raison")
        detail = Report.action_moderation_decide(report.id, "dismiss", "Rien")
        self.assertEqual(detail["state"], "dismissed")
        self.assertFalse(self.Notice.sudo().search([]))
        self.assertEqual(
            self.Report.with_user(self.france).linkup_my_reports()[0][
                "progress"
            ],
            "closed",
        )
        self.assertIn(report.id, self._queue_ids(self.joanna, "closed"))

    def test_hide_a_message(self):
        """A hidden message reaches every member of the thread without its
        text nor its attachments, by every path; the console keeps the
        original (LU-F-116 CA1)."""
        message = self._post(self.sam, "Texte blessant")
        attachment = self.env["ir.attachment"].create(
            {
                "name": "image.png",
                "raw": b"x",
                "res_model": "discuss.channel",
                "res_id": self.workshop.id,
            }
        )
        message.sudo().attachment_ids = attachment
        report = self._report(self.france, message_id=message.id)
        self._bus_reset()
        self._decide(self.joanna, report, "hide", "Propos blessants")
        # The search of mail.message flushes its access fields only, the
        # decision being committed before any other request.
        self.env.flush_all()
        self.assertTrue(message.linkup_hidden)
        self.assertFalse(message.attachment_ids)
        self.assertEqual(attachment.res_model, "linkup.hidden.content")
        for member in (self.sam, self.france, self.jacques):
            row = message.with_user(member).read(["body"])[0]
            self.assertFalse(row["body"])
            self.assertFalse(
                self.env["mail.message"]
                .with_user(member)
                .search([("body", "ilike", "blessant")])
            )
            with self.assertRaises(AccessError):
                attachment.with_user(member).read(["raw"])
        data = Store(message).get_result()["mail.message"][0]
        self.assertTrue(data["linkup_hidden"])
        self.assertFalse(data["body"])
        sent = [
            payload
            for target, kind, payload in self._bus_sent()
            if target == self.workshop and kind == "mail.record/insert"
        ]
        self.assertTrue(
            any(
                row.get("linkup_hidden")
                for payload in sent
                for row in payload.get("mail.message", [])
            )
        )
        notice = self.Notice.with_user(self.sam).search([])
        self.assertEqual(notice.decision, "hidden")
        # Its author neither shows it again nor writes a new body in it.
        with self.assertRaises(AccessError):
            message.with_user(self.sam).write({"linkup_hidden": False})
        with self.assertRaises(UserError):
            self.workshop.with_user(self.sam).sudo()._message_update_content(
                message, "<p>Autre texte</p>"
            )
        self.assertTrue(message.linkup_hidden)
        self.assertFalse(message.body)
        content = self._as(self.jean).linkup_moderation_content(report.id)
        reported = [item for item in content["items"] if item["reported"]]
        self.assertEqual(reported[0]["text"], "Texte blessant")
        self.assertTrue(reported[0]["hidden"])

    def test_hide_a_reflection_and_reverse_on_appeal(self):
        """A hidden reflection reads without its texts for both parties;
        a reversed appeal puts them back."""
        reflet = self._sent()
        report = self._report(self.france, reflet_id=reflet.id)
        self._decide(self.joanna, report, "hide", "Contenu")
        for member in (self.sam, self.france):
            row = reflet.with_user(member).read(["you_said", "understood"])[0]
            self.assertFalse(row["you_said"])
            self.assertFalse(row["understood"])
        values = reflet._linkup_card_values()
        self.assertTrue(values["moderation_hidden"])
        self.assertFalse(values["you_said"])
        self.assertTrue(reflet.message_id.linkup_hidden)
        notice = self.Notice.with_user(self.sam).search([])
        notice.with_user(self.sam).action_appeal("Je n'ai rien dit de tel.")
        self.assertEqual(report.state, "appealed")
        # The moderator who decided does not process the appeal.
        self.assertNotIn(report.id, self._queue_ids(self.joanna))
        self.assertIn(report.id, self._queue_ids(self.jean))
        detail = self._as(self.jean).linkup_moderation_detail(report.id)
        self.assertEqual(detail["appeal_text"], "Je n'ai rien dit de tel.")
        self._as(self.jean).action_moderation_resolve_appeal(
            report.id, False, "Erreur"
        )
        self.assertEqual(report.state, "dismissed")
        self.assertEqual(
            reflet.with_user(self.sam).you_said,
            "Que tu cherches du temps pour ton jardin.",
        )
        self.assertFalse(reflet.linkup_moderation_hidden)
        self.assertFalse(reflet.message_id.linkup_hidden)
        self.assertEqual(notice.appeal_state, "reversed")
        self.assertFalse(self.env["linkup.hidden.content"].sudo().search([]))
        with self.assertLinkupCode("linkup.validation"):
            notice.with_user(self.sam).action_appeal("Encore.")

    def test_warn_suspend_and_appeal_rules(self):
        """A warning and a suspension reach the member as notices; only the
        member contests theirs, once."""
        warned = self._report(self.france, user_id=self.sam.id)
        self._decide(self.joanna, warned, "warn", "Avertissement")
        suspended = self._report(self.jacques, user_id=self.sam.id)
        self._decide(self.joanna, suspended, "suspend", "Récidive", days=3)
        self.assertTrue(self.sam._linkup_is_suspended())
        notices = self.Notice.with_user(self.sam).search([], order="id")
        self.assertEqual(notices.mapped("decision"), ["warning", "suspended"])
        self.assertTrue(notices[1].suspended_until)
        infos = self.Notice.with_user(self.sam).linkup_my_notices()
        self.assertEqual(len(infos), 2)
        self.assertTrue(all(info["can_appeal"] for info in infos))
        self.assertFalse(self.Notice.with_user(self.france).search([]))
        with self.assertLinkupCode("linkup.unavailable"):
            notices[1].with_user(self.france).action_appeal("Pour Sam")
        with self.assertLinkupCode("linkup.validation"):
            notices[1].with_user(self.sam).action_appeal("  ")
        notices[1].with_user(self.sam).action_appeal("Trop sévère")
        self._as(self.jean).action_moderation_resolve_appeal(
            suspended.id, False, "Levée"
        )
        self.assertFalse(self.sam._linkup_is_suspended())
        self.assertEqual(self.sam.sudo().linkup_suspended_until, False)
        # The warning is contested and upheld.
        notices[0].with_user(self.sam).action_appeal("Je conteste")
        self._as(self.jean).action_moderation_resolve_appeal(
            warned.id, True, "Maintenu"
        )
        self.assertEqual(warned.state, "actioned")
        self.assertEqual(notices[0].appeal_state, "upheld")
        self.assertEqual(self.Notice._linkup_unseen_count(self.sam), 2)
        self.Notice.with_user(self.sam).action_mark_seen()
        self.assertEqual(self.Notice._linkup_unseen_count(self.sam), 0)

    def test_ban(self):
        """A ban closes the account, keeps a hash of the address 24 months,
        and tells the person by email; an administrator is not banned
        (LU-F-116 RM2, RM6)."""
        email = self.sam.email
        report = self._report(self.france, user_id=self.sam.id)
        self._decide(self.joanna, report, "ban", "Menaces répétées")
        self.assertFalse(self.sam.active)
        Blocklist = self.env["linkup.email.blocklist"]
        self.assertTrue(Blocklist._linkup_is_listed(email, "banned"))
        self.assertFalse(Blocklist._linkup_is_listed(email, "invite_optout"))
        mail = self._mails_to(email)[-1:]
        self.assertIn("closed", mail.subject)
        self.assertNotIn("France", mail.body_html)
        notice = self.Notice.sudo().search([("user_id", "=", self.sam.id)])
        self.assertEqual(notice.decision, "banned")
        self.assertFalse(notice._linkup_can_appeal())
        about_admin = self._report(self.france, user_id=self.jacques.id)
        self.jacques.groups_id |= self.env.ref(ADMIN)
        with self.assertLinkupCode("linkup.validation", field="decision"):
            self._decide(self.joanna, about_admin, "ban", "Non")

    def test_report_by_partner(self):
        """A member is reported by their partner, as Discuss knows them;
        an unknown partner reads as an unavailable member."""
        report = self._report(
            self.france, partner_id=self.jacques.partner_id.id
        )
        self.assertEqual(report.reported_user_id, self.jacques)
        with self.assertLinkupCode("linkup.unavailable"):
            self._report(self.france, partner_id=self.luce.partner_id.id)
        with self.assertLinkupCode("linkup.unavailable"):
            self._report(self.france, partner_id=999999)


@tagged("post_install", "-at_install")
class TestLinkupModerationUrgency(LinkupModerationMixin, LinkupCommunityCase):
    def test_urgent_report_reaches_the_moderators_without_conflict(self):
        """A report of a person in distress is urgent, due within the
        urgent delay, and reaches the moderators who may process it, by bus
        and by an email that names neither the reporter nor the content
        (LU-F-114 RM3, RM4, LU-F-118 CA2)."""
        self._bus_reset()
        report = self._report(
            self.france,
            user_id=self.sam.id,
            reason="distress",
            description="Elle parle de disparaître.",
        )
        self.assertTrue(report.urgent)
        hours = (report.due_date - report.create_date).total_seconds() / 3600
        self.assertAlmostEqual(hours, 24, delta=0.1)
        sent = [
            (target, payload)
            for target, kind, payload in self._bus_sent()
            if kind == "linkup.moderation/urgent"
        ]
        targets = {target for target, _payload in sent}
        expected = (self.joanna | self.jean | self.henri).partner_id
        self.assertTrue(set(expected) <= targets)
        for user in (self.thomas, self.sam, self.france, self.jacques):
            self.assertNotIn(user.partner_id, targets)
        self.assertEqual({tuple(payload) for _t, payload in sent}, {("id",)})
        mail = self._mails_to(self.joanna.email)
        self.assertEqual(len(mail), 1)
        for secret in ("France", "Sam", "disparaître", "distress"):
            self.assertNotIn(secret, mail.body_html)
            self.assertNotIn(secret, mail.subject)
        self.assertFalse(self._mails_to(self.thomas.email))
        # The reported member hears of nothing.
        self.assertFalse(
            [t for t, _k, _p in self._bus_sent() if t == self.sam.partner_id]
        )
        self.assertFalse(self.Report.with_user(self.sam).search([]))
        summary = self._as(self.joanna).linkup_moderation_summary()
        self.assertEqual((summary["open"], summary["urgent"]), (1, 1))

    def test_not_urgent_report(self):
        report = self._report(self.france, user_id=self.sam.id, reason="spam")
        self.assertFalse(report.urgent)
        hours = (report.due_date - report.create_date).total_seconds() / 3600
        self.assertAlmostEqual(hours, 72, delta=0.1)
        self.assertFalse(self._mails_to(self.joanna.email))

    def test_notice_tells_nothing_of_the_reporter(self):
        """The decision the member reads names neither who reported nor
        what they wrote."""
        report = self._report(
            self.france, user_id=self.sam.id, description="Il insiste."
        )
        self._decide(self.joanna, report, "warn", "Rappel")
        info = self.Notice.with_user(self.sam).linkup_my_notices()[0]
        self.assertEqual(
            set(info),
            {
                "id",
                "date",
                "decision",
                "reason",
                "suspended_until",
                "appeal_state",
                "can_appeal",
                "seen",
            },
        )
        notice = self.Notice.with_user(self.sam).search([])
        with self.assertRaises(AccessError):
            notice.read(["report_id"])
        profile = self.Users.with_user(self.sam).linkup_profile_info()
        self.assertEqual(len(profile["notices"]), 1)
        self.assertFalse(profile["reports"])
        self.assertNotIn("Il insiste.", str(profile))
        self.assertNotIn("France", str(profile))

    def test_store_holds_the_help(self):
        """The web client reads the resources, the hours and the delay of
        the help in distress (LU-F-118 RM2, LU-NF-042)."""
        params = self.env["ir.config_parameter"].sudo()
        params.set_param("linkup.help_resources", "Ligne A\n\n Ligne B ")
        params.set_param("linkup.moderation_hours", "9 h à 21 h")
        store = Store()
        self.env["res.users"].with_user(self.sam)._init_store_data(store)
        data = store.get_result()["Store"]
        self.assertEqual(data["linkup_help_resources"], ["Ligne A", "Ligne B"])
        self.assertEqual(data["linkup_moderation_hours"], "9 h à 21 h")
        self.assertEqual(data["linkup_urgent_hours"], 24)
        self.assertFalse(data["linkup_is_moderator"])
        self.assertNotIn("linkup_moderation_urgent", data)
        self._report(self.france, user_id=self.sam.id, reason="threat")
        store = Store()
        self.env["res.users"].with_user(self.joanna)._init_store_data(store)
        data = store.get_result()["Store"]
        self.assertTrue(data["linkup_is_moderator"])
        self.assertEqual(data["linkup_moderation_urgent"], 1)


@tagged("post_install", "-at_install")
class TestLinkupModerationRoutes(
    LinkupModerationMixin, LinkupCommunityCase, HttpCase
):
    def test_hidden_message_through_discuss(self):
        """``/discuss/channel/messages`` serves a hidden message without its
        text (LU-F-116 CA1)."""
        message = self._post(self.sam, "Texte à masquer")
        report = self._report(self.france, message_id=message.id)
        self._decide(self.joanna, report, "hide", "Masqué")
        self.authenticate(self.jacques.login, self.jacques.login)
        result = self.make_jsonrpc_request(
            "/discuss/channel/messages",
            {"channel_id": self.workshop.id, "limit": 30},
        )
        rows = {row["id"]: row for row in result["data"]["mail.message"]}
        self.assertTrue(rows[message.id]["linkup_hidden"])
        self.assertFalse(rows[message.id]["body"])
        self.assertNotIn("masquer", str(result))

    def test_report_and_block_routes(self):
        """``/linkup/v1/report`` and ``/linkup/v1/block`` delegate to the
        models (§9.8)."""
        self.authenticate(self.france.login, self.france.login)
        result = self.make_jsonrpc_request(
            "/linkup/v1/report",
            {"user_id": self.sam.id, "reason": "threat"},
        )
        self.assertTrue(result["urgent"])
        self.assertEqual(result["urgent_hours"], 24)
        report = self.Report.sudo().browse(result["id"])
        self.assertEqual(report.reporter_id, self.france)
        result = self.make_jsonrpc_request(
            "/linkup/v1/block", {"user_id": self.sam.id, "blocked": True}
        )
        self.assertEqual(result, {"blocked": True})
        self.assertTrue(
            self.env["linkup.block"]._linkup_has_blocked(self.france, self.sam)
        )
        self.make_jsonrpc_request(
            "/linkup/v1/block", {"user_id": self.sam.id, "blocked": False}
        )
        self.assertFalse(
            self.env["linkup.block"]._linkup_has_blocked(self.france, self.sam)
        )
