from odoo import http
from odoo.http import request


class TdmController(http.Controller):
    @http.route(
        ["/tdm/tdm_entrevue/<int:tdm_entrevue>"],
        type="http",
        auth="public",
        website=True,
    )
    def get_page_tdm_entrevue(self, tdm_entrevue=None):
        env = request.env(context=dict(request.env.context))

        tdm_entrevue_cls = env["tdm.entrevue"]
        if tdm_entrevue:
            tdm_entrevue_id = (
                tdm_entrevue_cls.sudo().browse(tdm_entrevue).exists()
            )
        else:
            tdm_entrevue_id = None
        dct_value = {"tdm_entrevue_id": tdm_entrevue_id}

        # Render page
        return request.render("tdm.tdm_entrevue_unit", dct_value)

    @http.route(
        ["/tdm/tdm_offre_emploi/<int:tdm_offre_emploi>"],
        type="http",
        auth="public",
        website=True,
    )
    def get_page_tdm_offre_emploi(self, tdm_offre_emploi=None):
        env = request.env(context=dict(request.env.context))

        tdm_offre_emploi_cls = env["tdm.offre.emploi"]
        if tdm_offre_emploi:
            tdm_offre_emploi_id = (
                tdm_offre_emploi_cls.sudo().browse(tdm_offre_emploi).exists()
            )
        else:
            tdm_offre_emploi_id = None
        dct_value = {"tdm_offre_emploi_id": tdm_offre_emploi_id}

        # Render page
        return request.render("tdm.tdm_offre_emploi_unit", dct_value)

    @http.route(
        ["/tdm/tdm_offre_emploi_applique/<int:tdm_offre_emploi_applique>"],
        type="http",
        auth="public",
        website=True,
    )
    def get_page_tdm_offre_emploi_applique(
        self, tdm_offre_emploi_applique=None
    ):
        env = request.env(context=dict(request.env.context))

        tdm_offre_emploi_applique_cls = env["tdm.offre.emploi.applique"]
        if tdm_offre_emploi_applique:
            tdm_offre_emploi_applique_id = (
                tdm_offre_emploi_applique_cls.sudo()
                .browse(tdm_offre_emploi_applique)
                .exists()
            )
        else:
            tdm_offre_emploi_applique_id = None
        dct_value = {
            "tdm_offre_emploi_applique_id": tdm_offre_emploi_applique_id
        }

        # Render page
        return request.render("tdm.tdm_offre_emploi_applique_unit", dct_value)

    @http.route(
        [
            "/tdm/tdm_entrevue_and_tdm_offre_emploi_and_tdm_offre_emploi_applique_list"
        ],
        type="json",
        auth="public",
        website=True,
    )
    def get_tdm_entrevue_and_tdm_offre_emploi_and_tdm_offre_emploi_applique_list(
        self,
    ):
        env = request.env(context=dict(request.env.context))

        tdm_entrevue_cls = env["tdm.entrevue"]
        tdm_entrevue_ids = tdm_entrevue_cls.sudo().search([]).ids
        tdm_entrevue_s = tdm_entrevue_cls.sudo().browse(tdm_entrevue_ids)

        tdm_offre_emploi_cls = env["tdm.offre.emploi"]
        tdm_offre_emploi_ids = tdm_offre_emploi_cls.sudo().search([]).ids
        tdm_offre_emploi_s = tdm_offre_emploi_cls.sudo().browse(
            tdm_offre_emploi_ids
        )

        tdm_offre_emploi_applique_cls = env["tdm.offre.emploi.applique"]
        tdm_offre_emploi_applique_ids = (
            tdm_offre_emploi_applique_cls.sudo().search([]).ids
        )
        tdm_offre_emploi_applique_s = (
            tdm_offre_emploi_applique_cls.sudo().browse(
                tdm_offre_emploi_applique_ids
            )
        )

        dct_value = {
            "tdm_entrevue_s": tdm_entrevue_s,
            "tdm_offre_emploi_s": tdm_offre_emploi_s,
            "tdm_offre_emploi_applique_s": tdm_offre_emploi_applique_s,
        }

        # Render page
        return request.env["ir.ui.view"].render_template(
            "tdm.tdm_entrevue_and_tdm_offre_emploi_and_tdm_offre_emploi_applique_list",
            dct_value,
        )
