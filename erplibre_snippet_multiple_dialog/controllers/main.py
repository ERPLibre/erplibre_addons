from odoo import http
from odoo.http import request


class ErplibreSnippetMultipleDialogController(http.Controller):
    @http.route(
        ["/erplibre_snippet_multiple_dialog/get_last_item"],
        type="json",
        auth="public",
        website=True,
        methods=["POST", "GET"],
        csrf=False,
    )
    def get_last_item(self):
        data_id = http.request.env["sinerkia_jitsi_meet.jitsi_meet"].search(
            [], order="create_date desc", limit=1
        )
        dct_value = {}
        if data_id:
            dct_value["closed"] = data_id.closed
            dct_value["date"] = data_id.date
            dct_value["date_delay"] = data_id.date_delay
            dct_value["hash"] = data_id.hash
            dct_value["name"] = data_id.name
            dct_value["url"] = data_id.url
        return dct_value
