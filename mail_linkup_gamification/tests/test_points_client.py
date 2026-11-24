# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""What the server gives the web client of the points: the filters of "My
points", the lines newer than a known one, the scale and the newest line in
the Store, the energy of a link in the LinkUp panel, the id of each line on
the bus, and the setting that hides the points (LU-F-071, LU-F-091,
LU-F-103)."""

from odoo.addons.mail.tools.discuss import Store
from odoo.tests import tagged

from .common import LinkupPointsCase


@tagged("post_install", "-at_install")
class TestLinkupPointsClient(LinkupPointsCase):
    def test_my_points_filters(self):
        """ "My points" keeps the lines of one rule or of one person, and
        lists the scale and the people the member shares lines with."""
        self._confirmed()
        self._confirmed_by(self.sam, self.jacques)
        Ledger = self.Ledger.with_user(self.sam)
        everything = Ledger.linkup_my_points()
        self.assertEqual(everything["total"], 4)
        self.assertEqual(
            [person["name"] for person in everything["counterparts"]],
            ["France", "Jacques"],
        )
        scale = {rule["code"]: rule["points"] for rule in everything["rules"]}
        self.assertEqual(scale["reflect_confirmed"], 1000)
        self.assertEqual(scale["reflect_rejected"], -150)
        self.assertNotIn("highlight", scale, "a rule paying nobody")
        sent = Ledger.linkup_my_points(rule_code="reflect_sent")
        self.assertEqual(sent["total"], 2)
        self.assertEqual(
            {line["rule_code"] for line in sent["lines"]}, {"reflect_sent"}
        )
        with_jacques = Ledger.linkup_my_points(counterpart_id=self.jacques.id)
        self.assertEqual(with_jacques["total"], 2)
        self.assertEqual(
            {line["counterpart"]["id"] for line in with_jacques["lines"]},
            {self.jacques.id},
        )
        both = Ledger.linkup_my_points(
            rule_code="reflect_confirmed", counterpart_id=self.france.id
        )
        self.assertEqual(both["total"], 1)

    def test_my_points_after_a_line(self):
        """``after_id`` gives the lines newer than a known one, oldest
        first: the web client reads with it the points of an action."""
        self._confirmed()
        Ledger = self.Ledger.with_user(self.sam)
        known = Ledger.linkup_my_points()["last_id"]
        self.assertEqual(known, max(self._lines(self.sam).ids))
        self.assertEqual(Ledger.linkup_my_points(after_id=known)["lines"], [])
        self._confirmed_by(self.sam, self.jacques)
        newer = Ledger.linkup_my_points(after_id=known)
        ids = [line["id"] for line in newer["lines"]]
        self.assertEqual(len(ids), 2)
        self.assertEqual(ids, sorted(ids))
        self.assertTrue(all(line_id > known for line_id in ids))
        self.assertEqual(newer["balance"], 2200)

    def test_my_points_ignores_bad_arguments(self):
        """Arguments that are not numbers read the first page."""
        self._confirmed()
        points = self.Ledger.with_user(self.sam).linkup_my_points(
            limit="x", after_id="y"
        )
        self.assertEqual(points["total"], 2)

    def test_store_gives_the_scale_and_the_newest_line(self):
        """The Store of a member holds the points of each rule, for the
        texts of the guide, and the id of their newest line."""
        store = Store()
        self.env["res.users"].with_user(self.sam)._init_store_data(store)
        data = store.get_result()["Store"]
        self.assertEqual(data["linkup_points_last_id"], 0)
        self.assertEqual(
            data["linkup_points_rules"]["reflect_confirmed"], 1000
        )
        self.assertEqual(data["linkup_points_rules"]["reflect_rejected"], -150)
        self._confirmed()
        store = Store()
        self.env["res.users"].with_user(self.sam)._init_store_data(store)
        self.assertEqual(
            store.get_result()["Store"]["linkup_points_last_id"],
            max(self._lines(self.sam).ids),
        )

    def test_awarded_carries_the_line_id(self):
        """Each line on the bus carries its id, so that the web client
        shows it once."""
        self._bus_reset()
        self._confirmed()
        payloads = self._awarded(self.france)
        self.assertEqual(
            [payload["id"] for payload in payloads],
            self._lines(self.france).ids,
        )

    def test_channel_info_gives_the_energy_of_the_link(self):
        """LU-F-071 RM2: the LinkUp panel reads the energy of the link as
        its reader received it."""
        reflet = self._confirmed()
        channel_id = reflet.channel_id.id
        Reflet = self.env["linkup.reflet"]
        self.assertEqual(
            Reflet.with_user(self.sam).linkup_channel_info(channel_id)[
                "link_energy"
            ],
            1100,
        )
        self.assertEqual(
            Reflet.with_user(self.france).linkup_channel_info(channel_id)[
                "link_energy"
            ],
            1000,
        )

    def test_hide_gamification_setting(self):
        """A member hides the points from their own settings, which reach
        the web client; nothing is hidden by default."""
        settings = self.env["res.users.settings"]._find_or_create_for_user(
            self.sam
        )
        self.assertFalse(settings.linkup_hide_gamification)
        settings.with_user(self.sam).set_res_users_settings(
            {"linkup_hide_gamification": True}
        )
        self.assertTrue(settings.linkup_hide_gamification)
        self.assertTrue(
            settings._res_users_settings_format()["linkup_hide_gamification"]
        )
