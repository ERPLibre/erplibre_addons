from odoo import http
from odoo.http import request


class DemoWebsiteSnippetController(http.Controller):
    @http.route(
        ["/demo_website_snippet/helloworld"],
        type="json",
        auth="public",
        website=True,
        methods=["POST", "GET"],
        csrf=False,
    )
    def hello_world(self):
        result_ids = request.env["demo.model.internal"].search([])
        lst_fruit = []
        data = {"fruit": lst_fruit}
        for result_id in result_ids:
            lst_fruit.append(result_id.name)
        return data