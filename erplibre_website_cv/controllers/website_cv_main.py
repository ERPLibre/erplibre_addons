from odoo import http, models, fields, api
from odoo.http import request

import json
import werkzeug


class WebsiteCVController(http.Controller):
    @http.route(
        ["/erplibre_website_cv/website_cv"],
        type="json",
        auth="public",
        website=True,
        methods=["POST", "GET"],
        csrf=False,
    )
    # Ajout des fruits du demo_internal
    def website_cv(self):
        result_ids = request.env["website.cv"].search([])
        lst_fruit = []
        data = {"fruit": lst_fruit}
        for result_id in result_ids:
            lst_fruit.append(result_id.name)
        return data

    @http.route(
        "/erplibre_website_cv/add",
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=False,
    )
    def submit_website_cv_portal(self, **kw):
        vals = {}

        if kw.get("ypos"):
            ypos_value = kw.get("ypos")
            vals["name"] = str(ypos_value)

        new_website_cv_portal = (
            request.env["website.cv"].sudo().create(vals)
        )
