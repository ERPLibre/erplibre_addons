# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""The route of the screen "My points" (§9.8, LU-F-103)."""

from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.addons.mail_linkup_reflet.tests.common import MEMBER
from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestLinkupPointsRoutes(HttpCase):
    def test_me_points(self):
        """``/linkup/v1/me/points`` gives the points of the member who
        calls it, page by page."""
        sam = mail_new_test_user(
            self.env,
            login="linkup_rt_sam",
            name="Sam",
            email="linkup_rt_sam@example.com",
            groups=MEMBER,
        )
        self.authenticate("linkup_rt_sam", "linkup_rt_sam")
        result = self.make_jsonrpc_request(
            "/linkup/v1/me/points", {"limit": 10, "offset": 0}
        )
        self.assertEqual(result["balance"], sam.karma)
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["lines"], [])
        self.assertFalse(result["rank"])
