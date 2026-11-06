# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""The routes of the Network view (§9.8)."""

from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.addons.mail_linkup_reflet.tests.common import MEMBER
from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestLinkupNetworkRoutes(HttpCase):
    def test_network_routes(self):
        """``/linkup/v1/network/graph``, ``ranking`` and ``link`` answer
        for the member who calls them; an error carries its code."""

        def member(login, name):
            return mail_new_test_user(
                self.env,
                login=login,
                password=login,
                name=name,
                email=f"{login}@example.com",
                groups=MEMBER,
            )

        sam = member("linkup_nr_sam", "Sam")
        france = member("linkup_nr_france", "France")
        link = self.env["linkup.link"]._get_or_create(sam, france)
        link._linkup_activate()
        self.authenticate("linkup_nr_sam", "linkup_nr_sam")
        graph = self.make_jsonrpc_request(
            "/linkup/v1/network/graph", {"level": "x2", "limit": 10}
        )
        self.assertEqual(graph["level"], "x2")
        self.assertEqual(graph["me"]["user_id"], sam.id)
        self.assertEqual(
            [node["user_id"] for node in graph["nodes"]], [france.id]
        )
        ranking = self.make_jsonrpc_request(
            "/linkup/v1/network/ranking", {"kind": "partners", "period": "all"}
        )
        self.assertEqual(
            [(row["user_id"], row["value"]) for row in ranking["rows"]],
            [(france.id, 0)],
        )
        card = self.make_jsonrpc_request(
            "/linkup/v1/network/link", {"user_id": france.id}
        )
        self.assertTrue(card["available"])
        self.assertEqual(card["energy"], 0)
        self.assertEqual(
            self.make_jsonrpc_request(
                "/linkup/v1/network/link", {"user_id": 0}
            ),
            {"available": False},
        )
        response = self.url_open(
            "/linkup/v1/network/ranking",
            data='{"jsonrpc": "2.0", "method": "call",'
            ' "params": {"kind": "community"}}',
            headers={"Content-Type": "application/json"},
        )
        error = response.json()["error"]
        self.assertEqual(
            error["data"]["context"]["linkup_code"], "linkup.validation"
        )
