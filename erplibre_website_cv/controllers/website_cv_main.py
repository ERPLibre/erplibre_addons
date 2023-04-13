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
    def get_informations(self):
        informations_response = http.request.env["website.cv"].search([])
        informations = list()
        for information in informations_response:
            informations.append({
                "id": information["id"],
                "name": information["name"]
            })
        return informations

    @http.route(
        "/erplibre_website_cv/website_update",
        type="json",
        auth="public",
        website=True,
        methods=["POST"],
        csrf=False,
    )
    def update_aliment(self, **kwargs):
        informations_id, informations_name = kwargs.get(
            "informations_id"), kwargs.get("informations_name")

        if not informations_id:
            return False

        matching_informations = http.request.env["website.cv"].search(
            [("id", "=", informations_id)], limit=1)
        matching_informations.write({"name": informations_name})
        return True
