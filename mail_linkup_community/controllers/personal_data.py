# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import json

from odoo import fields, http
from odoo.http import content_disposition, request


class LinkupPersonalDataController(http.Controller):
    """The routes of the personal data of the current member (§9.8).

    ``/linkup/v1/me/export`` downloads, as a JSON file, what
    ``res.users.linkup_export_data`` gathers for the session user only: the
    route takes no identifier. ``/linkup/v1/me/delete`` asks for the
    deletion of the account, or cancels it with ``cancel``.
    """

    @http.route(
        "/linkup/v1/me/export", type="http", auth="user", methods=["GET"]
    )
    def linkup_me_export(self):
        data = request.env["res.users"].linkup_export_data()
        body = json.dumps(data, ensure_ascii=False, indent=2)
        filename = f"linkup-{fields.Date.context_today(request.env.user)}.json"
        return request.make_response(
            body,
            headers=[
                ("Content-Type", "application/json; charset=utf-8"),
                ("Content-Disposition", content_disposition(filename)),
                ("Cache-Control", "no-store"),
                ("X-Content-Type-Options", "nosniff"),
            ],
        )

    @http.route(
        "/linkup/v1/me/delete", type="json", auth="user", methods=["POST"]
    )
    def linkup_me_delete(self, cancel=False):
        """Return the deletion as the profile reads it: the date asked and
        the date of the erasure, ``False`` once cancelled."""
        Users = request.env["res.users"]
        if cancel:
            return Users.linkup_cancel_deletion()
        return Users.linkup_request_deletion()
