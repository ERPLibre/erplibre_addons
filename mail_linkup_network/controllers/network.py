# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Routes of the Network view (§9.8): each one delegates to a method of
``linkup.link``, which checks the member and their scope."""

from odoo import http
from odoo.http import request


class LinkupNetworkController(http.Controller):
    @http.route(
        "/linkup/v1/network/graph", type="json", auth="user", methods=["POST"]
    )
    def linkup_network_graph(self, level="x1", limit=50, **kwargs):
        """The graph of the current member, as
        ``linkup.link.get_network_graph`` gives it."""
        return request.env["linkup.link"].get_network_graph(
            level=level, limit=limit
        )

    @http.route(
        "/linkup/v1/network/ranking",
        type="json",
        auth="user",
        methods=["POST"],
    )
    def linkup_network_ranking(self, kind="partners", period="all", **kwargs):
        """A ranking of the contacts of the current member, as
        ``linkup.link.get_ranking`` gives it."""
        return request.env["linkup.link"].get_ranking(kind=kind, period=period)

    @http.route(
        "/linkup/v1/network/link", type="json", auth="user", methods=["POST"]
    )
    def linkup_network_link(
        self, user_id=None, reflets_only=False, limit=20, **kwargs
    ):
        """The card of the link with a contact, as
        ``linkup.link.get_link_card`` gives it."""
        return request.env["linkup.link"].get_link_card(
            user_id, reflets_only=reflets_only, limit=limit
        )
