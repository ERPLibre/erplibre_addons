# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import http
from odoo.http import request


class LinkupPointsController(http.Controller):
    @http.route(
        "/linkup/v1/me/points", type="json", auth="user", methods=["POST"]
    )
    def linkup_me_points(
        self,
        limit=50,
        offset=0,
        rule_code=False,
        counterpart_id=False,
        after_id=False,
        **kwargs,
    ):
        """The points of the current member, as
        ``linkup.points.ledger.linkup_my_points`` gives them."""
        return request.env["linkup.points.ledger"].linkup_my_points(
            limit=limit,
            offset=offset,
            rule_code=rule_code,
            counterpart_id=counterpart_id,
            after_id=after_id,
        )
