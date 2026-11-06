# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Karma, ranks, badges, native gamification and the screen "My points"
(LU-F-071, LU-F-100 to LU-F-103, LU-NF-033, LU-NF-043, T-47)."""

from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.addons.mail.tools.discuss import Store
from odoo.addons.mail_linkup_gamification import uninstall_hook
from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tools import html2plaintext, mute_logger

from .common import LinkupPointsCase

ADMIN_GROUP = "mail_linkup_reflet.group_linkup_admin"


@tagged("post_install", "-at_install")
class TestLinkupPointsGamification(LinkupPointsCase):
    def _badges(self, user):
        return user.sudo().badge_ids.badge_id

    def _badge(self, name):
        return self.env.ref(f"mail_linkup_gamification.{name}")

    # Badges and ranks (LU-F-102)

    def test_first_link_badge_once(self):
        """LU-F-102 CA1: the first confirmation gives "First link" to both,
        once; the author also gets "First reflection"."""
        self._bus_reset()
        self._confirmed()
        self._confirmed()
        first_link = self._badge("badge_first_link")
        for user in (self.sam, self.france):
            badges = user.sudo().badge_ids.filtered(
                lambda badge_user: badge_user.badge_id == first_link
            )
            self.assertEqual(len(badges), 1)
        self.assertIn(
            self._badge("badge_first_reflection"), self._badges(self.sam)
        )
        self.assertNotIn(
            self._badge("badge_first_reflection"), self._badges(self.france)
        )
        sent = [
            payload["badge_id"]
            for target, kind, payload in self._bus_sent()
            if kind == "linkup.points/badge"
            and target == self.france.partner_id
        ]
        self.assertEqual(sent, [first_link.id])

    def test_guess_and_call_badges(self):
        """The guess badge goes to the member who guessed; the call badge
        to both."""
        reflet = self._confirmed()
        precision = self._child(
            reflet.with_user(self.france).action_answer_precision(
                "Je voudrais préciser.", [self.goals.id]
            )
        )
        precision.with_user(self.sam).action_guess(self.goals.id)
        guess = self._badge("badge_first_guess")
        self.assertIn(guess, self._badges(self.sam))
        self.assertNotIn(guess, self._badges(self.france))
        sam, france = self._call_members(reflet)
        sam._rtc_join_call()
        france._rtc_join_call()
        call = self._badge("badge_first_call")
        self.assertIn(call, self._badges(self.sam))
        self.assertIn(call, self._badges(self.france))

    def test_ten_links_badge(self):
        """ "Ten links" comes with the tenth linked member."""
        others = self._new_members(10, "ten")
        for other in others[:9]:
            self._confirmed_by(other, self.sam)
        self.assertNotIn(
            self._badge("badge_ten_links"), self._badges(self.sam)
        )
        self._confirmed_by(others[9], self.sam)
        self.assertIn(self._badge("badge_ten_links"), self._badges(self.sam))

    def test_rank_and_badge_send_no_email(self):
        """LU-F-102 CA2, T-47: a new rank and a badge send no email; the
        rank is announced on the bus."""
        mails = self.env["mail.mail"].sudo().search([])
        self._bus_reset()
        self._confirmed()
        self.assertEqual(
            self.sam.sudo().rank_id,
            self.env.ref("mail_linkup_gamification.rank_spark"),
        )
        self.assertTrue(self._badges(self.sam))
        self.assertEqual(self.env["mail.mail"].sudo().search([]), mails)
        ranks = [
            payload
            for target, kind, payload in self._bus_sent()
            if kind == "linkup.points/rank" and target == self.sam.partner_id
        ]
        self.assertEqual(ranks[-1]["name"], "Spark")

    def test_rank_lost_below_the_lowest(self):
        """§7.4: a karma that falls below the lowest rank leaves no rank."""
        self._confirmed()
        self.assertTrue(self.sam.sudo().rank_id)
        self._rule("reflect_rejected").points = -2000
        self._sent().with_user(self.france).action_reject()
        self.assertEqual(self.sam.sudo().karma, -900)
        self.assertFalse(self.sam.sudo().rank_id)
        self.assertEqual(
            self.sam.sudo().next_rank_id,
            self.env.ref("mail_linkup_gamification.rank_spark"),
        )

    def test_linkup_ranks_replace_the_native_ones(self):
        """LU-F-102 RM1: the native ranks are gone, and their external ids
        name the LinkUp ranks."""
        ranks = self.env["gamification.karma.rank"].search([])
        self.assertEqual(
            ranks.mapped("name"), ["Spark", "Flame", "Fire", "Blaze", "Sun"]
        )
        self.assertEqual(
            self.env.ref("gamification.rank_newbie"),
            self.env.ref("mail_linkup_gamification.rank_spark"),
        )

    def test_native_challenges_are_done(self):
        """LU-NF-033: the native challenges are closed, without users."""
        for xmlid in (
            "gamification.challenge_base_discover",
            "gamification.challenge_base_configure",
        ):
            challenge = self.env.ref(xmlid)
            self.assertEqual(challenge.state, "done")
            self.assertFalse(challenge.user_ids)

    # Ledger and karma (LU-F-100, LU-NF-043)

    def test_ledger_is_append_only(self):
        """LU-F-100: a line is never written, and only the superuser
        deletes it."""
        self._confirmed()
        line = self._lines(self.sam)[:1]
        with self.assertRaises(AccessError):
            line.write({"points": 5000})
        with self.assertRaises(AccessError):
            line.with_user(self.env.ref("base.user_admin")).unlink()

    def test_karma_check(self):
        """LU-NF-043: the daily check finds no difference, then the member
        whose karma moved outside the ledger."""
        self._confirmed()
        Ledger = self.Ledger.sudo()
        self.assertEqual(Ledger._cron_check_karma(), [])
        self.sam.sudo()._add_karma(7)
        with mute_logger(
            "odoo.addons.mail_linkup_gamification.models.linkup_points_ledger"
        ):
            self.assertEqual(Ledger._cron_check_karma(), [self.sam.id])

    def test_karma_alert_activity(self):
        """LU-NF-043: a difference gives each LinkUp administrator one
        to-do activity, which names the members by id only; the same
        difference adds none while it is open, a new one or a later check
        after it is done adds one."""
        admin = mail_new_test_user(
            self.env,
            login="linkup_pt_admin",
            name="Administrateur LinkUp",
            email="linkup_pt_admin@example.com",
            groups=ADMIN_GROUP,
        )
        todo = self.env.ref("mail.mail_activity_data_todo")
        Ledger = self.Ledger.sudo()
        Activity = self.env["mail.activity"].sudo()

        def alerts(user):
            return Activity.search(
                [
                    ("user_id", "=", user.id),
                    ("activity_type_id", "=", todo.id),
                    ("res_model", "=", "res.partner"),
                    ("res_id", "=", user.partner_id.id),
                ]
            )

        self._confirmed()
        Ledger._cron_check_karma()
        self.assertFalse(alerts(admin))
        self.sam.sudo()._add_karma(7)
        with mute_logger(
            "odoo.addons.mail_linkup_gamification.models.linkup_points_ledger"
        ):
            Ledger._cron_check_karma()
            Ledger._cron_check_karma()
        activity = alerts(admin)
        self.assertEqual(len(activity), 1)
        self.assertEqual(len(alerts(self.env.ref("base.user_admin"))), 1)
        self.assertFalse(
            Activity.search([("user_id", "in", self.members.ids)])
        )
        self.assertIn(str(self.sam.id), activity.summary)
        text = f"{activity.summary} {html2plaintext(activity.note)}"
        self.assertIn(str(self.sam.id), text)
        for value in (self.sam.name, self.sam.login, self.sam.email):
            self.assertNotIn(value, text)
        # Another difference is another alert.
        self.france.sudo()._add_karma(3)
        with mute_logger(
            "odoo.addons.mail_linkup_gamification.models.linkup_points_ledger"
        ):
            Ledger._cron_check_karma()
        self.assertEqual(len(alerts(admin)), 2)
        # Once done, the difference still found alerts again.
        alerts(admin).action_done()
        self.assertFalse(alerts(admin))
        with mute_logger(
            "odoo.addons.mail_linkup_gamification.models.linkup_points_ledger"
        ):
            Ledger._cron_check_karma()
        self.assertEqual(len(alerts(admin)), 1)

    def test_uninstall_takes_the_points_out_of_the_karma(self):
        """LU-NF-043: the uninstallation takes the points of the ledger out
        of the karma, which keeps what was earned outside LinkUp."""
        self._confirmed()
        self.sam.sudo()._add_karma(7)
        self.assertEqual(self.sam.sudo().karma, 1107)
        uninstall_hook(self.env)
        self.assertEqual(self.sam.sudo().karma, 7)
        self.assertEqual(self.france.sudo().karma, 0)
        self.assertFalse(self.france.sudo().rank_id)

    def test_badges_of_others_stay_hidden(self):
        """LU-F-102: a member reads their own badges only, and grants none;
        the holders of a badge never list the members of the instance."""
        self._confirmed()
        self._confirmed_by(self.jacques, self.france)
        BadgeUser = self.env["gamification.badge.user"].with_user(self.sam)
        self.assertEqual(BadgeUser.search([]).user_id, self.sam)
        other = self.jacques.sudo().badge_ids[:1]
        self.assertTrue(other)
        with self.assertRaises(AccessError):
            other.with_user(self.sam).read(["user_id"])
        with self.assertRaises(AccessError):
            BadgeUser.create(
                {
                    "user_id": self.france.id,
                    "badge_id": self.env.ref("gamification.badge_good_job").id,
                }
            )

    # Energy (LU-F-071)

    def test_energy_of_the_other_side_stays_hidden(self):
        """LU-F-071 RM2: a member reads their side of the energy through
        the server only; the side of the other member would tell the caps
        they reached elsewhere."""
        link = self._confirmed().link_id
        self.assertEqual(link._linkup_energy_for(self.sam), 1100)
        for field in ("energy_a", "energy_b"):
            with self.assertRaises(AccessError):
                link.with_user(self.sam).read([field])

    def test_energy_is_the_sum_of_the_lines_of_the_pair(self):
        """LU-F-071 CA2: the energy of a link, as each member reads it, is
        the sum of the points they received in the pair."""
        reflet = self._confirmed()
        exact = self._exact(reflet, self.france)
        self._continue(exact, self.sam)
        self._sent().with_user(self.france).action_reject()
        self._confirmed_by(self.jacques, self.sam)
        link = reflet.link_id
        for user in (self.sam, self.france):
            lines = self.Ledger.sudo().search(
                [("user_id", "=", user.id), ("link_id", "=", link.id)]
            )
            self.assertEqual(
                link._linkup_energy_for(user), sum(lines.mapped("points"))
            )
        self.assertEqual(link._linkup_energy_for(self.jacques), 0)

    # My points (LU-F-103)

    def test_my_points(self):
        """LU-F-103 CA1: Sam reads his lines, balance, rank and badges,
        never the lines of others."""
        self._confirmed()
        self._confirmed_by(self.jacques, self.france)
        Ledger = self.Ledger.with_user(self.sam)
        points = Ledger.linkup_my_points()
        self.assertEqual(points["balance"], 1100)
        self.assertEqual(points["total"], 2)
        self.assertEqual(points["rank"]["name"], "Spark")
        self.assertEqual(points["next_rank"]["karma_min"], 2500)
        self.assertEqual(
            {line["rule_code"] for line in points["lines"]},
            {"reflect_sent", "reflect_confirmed"},
        )
        self.assertEqual(
            {line["counterpart"]["id"] for line in points["lines"]},
            {self.france.id},
        )
        self.assertTrue(points["badges"])
        self.assertEqual(
            Ledger.search([]).user_id, self.sam, "a member reads own lines"
        )
        self.assertEqual(
            len(Ledger.linkup_my_points(limit=1, offset=1)["lines"]), 1
        )

    def test_store_gives_the_energy(self):
        """LU-F-071 RM1: the web client receives the karma and the rank of
        the member."""
        self._confirmed()
        store = Store()
        self.env["res.users"].with_user(self.sam)._init_store_data(store)
        data = store.get_result()["Store"]
        self.assertEqual(data["linkup_karma"], 1100)
        self.assertEqual(data["linkup_rank"], "Spark")
