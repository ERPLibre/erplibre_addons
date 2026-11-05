# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""The first-use tour (T-25, LU-F-083): its state "already seen" lives on
the user, the settings turn it off, and a LinkUp administrator shows it
again to every member.
"""

from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.addons.mail.tools.discuss import Store
from odoo.exceptions import AccessError

from .common import LinkupRefletCase

PARAM = "linkup.first_use_tour"


class TestLinkupFirstUseTour(LinkupRefletCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = cls.env.ref("base.user_admin")

    def _pending(self, user):
        store = Store()
        self.env["res.users"].with_user(user)._init_store_data(store)
        return store.get_result()["Store"]["linkup_tour_pending"]

    def test_pending_until_consumed(self):
        """A new member has the tour pending; once they finish or skip it,
        it is no longer pending, on any device, and for them only
        (LU-F-083 CA1, CA2)."""
        self.assertFalse(self.sam.linkup_tour_done)
        self.assertTrue(self._pending(self.sam))
        self.env["res.users"].with_user(self.sam).linkup_tour_consume()
        self.assertTrue(self.sam.linkup_tour_done)
        self.assertFalse(self._pending(self.sam))
        self.assertTrue(self._pending(self.france))

    def test_consume_reaches_the_other_clients(self):
        """A tour skipped in one client no longer starts in another client
        of the member already loaded: the new state goes over the bus, to
        the member only (LU-F-083 RM2)."""
        self._bus_reset()
        self.env["res.users"].with_user(self.sam).linkup_tour_consume()
        sent = [
            (target, payload)
            for target, kind, payload in self._bus_sent()
            if kind == "mail.record/insert"
            and "linkup_tour_pending" in payload.get("Store", {})
        ]
        self.assertEqual(len(sent), 1)
        target, payload = sent[0]
        self.assertEqual(target, self.sam.partner_id)
        self.assertIs(payload["Store"]["linkup_tour_pending"], False)

    def test_member_cannot_write_the_state(self):
        """The state is written by ``linkup_tour_consume`` only."""
        with self.assertRaises(AccessError):
            self.france.with_user(self.france).write(
                {"linkup_tour_done": True}
            )
        with self.assertRaises(AccessError):
            self.sam.with_user(self.france).write({"linkup_tour_done": True})

    def test_global_switch(self):
        """The setting turns the tour off for everyone, on by default."""
        Settings = self.env["res.config.settings"]
        self.assertTrue(Settings.create({}).linkup_first_use_tour)
        Settings.create({"linkup_first_use_tour": False}).execute()
        param = self.env["ir.config_parameter"].sudo().get_param(PARAM)
        self.assertEqual(param, "False")
        self.assertFalse(Settings.create({}).linkup_first_use_tour)
        self.assertFalse(self._pending(self.sam))
        Settings.create({"linkup_first_use_tour": True}).execute()
        self.assertTrue(self._pending(self.sam))

    def test_not_a_member(self):
        """A user outside LinkUp never has the tour pending."""
        employee = mail_new_test_user(
            self.env, login="linkup_tour_employee", groups="base.group_user"
        )
        self.assertFalse(self._pending(employee))

    def test_reset_for_all_members(self):
        """A LinkUp administrator shows the tour again to every member; a
        member cannot (LU-F-083 RM4)."""
        Users = self.env["res.users"]
        for user in (self.sam, self.france):
            Users.with_user(user).linkup_tour_consume()
        with self.assertRaises(AccessError):
            Users.with_user(self.sam)._linkup_reset_first_use_tour()
        action = (
            self.env["res.config.settings"]
            .with_user(self.admin)
            .create({})
            .action_linkup_reset_first_use_tour()
        )
        self.assertEqual(action["tag"], "display_notification")
        self.assertFalse(self.sam.linkup_tour_done)
        self.assertFalse(self.france.linkup_tour_done)
        self.assertTrue(self._pending(self.sam))
