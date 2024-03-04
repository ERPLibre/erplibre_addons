import base64
import logging

import werkzeug

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


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
        ["/tdm/tdm_offre_emploi_list"],
        type="json",
        auth="public",
        website=True,
    )
    def get_tdm_offre_emploi_list(self):
        env = request.env(context=dict(request.env.context))

        tdm_offre_emploi_cls = env["tdm.offre.emploi"]
        tdm_offre_emploi_ids = tdm_offre_emploi_cls.sudo().search([]).ids
        tdm_offre_emploi_s = tdm_offre_emploi_cls.sudo().browse(
            tdm_offre_emploi_ids
        )

        dct_value = {"tdm_offre_emploi_s": tdm_offre_emploi_s}

        # Render page
        return request.env["ir.ui.view"].render_template(
            "tdm.tdm_offre_emploi_list", dct_value
        )

    @http.route("/new/tdm_entrevue", type="http", auth="user", website=True)
    def create_new_tdm_entrevue(self, **kw):
        name = http.request.env.user.name
        default_date_debut_entrevue = (
            http.request.env["tdm.entrevue"]
            .default_get(["date_debut_entrevue"])
            .get("date_debut_entrevue")
        )
        offre_emploi_applique_id = http.request.env[
            "tdm.offre.emploi.applique"
        ].search([])
        default_offre_emploi_applique_id = (
            http.request.env["tdm.entrevue"]
            .default_get(["offre_emploi_applique_id"])
            .get("offre_emploi_applique_id")
        )
        offre_emploi_id = http.request.env["tdm.offre.emploi"].search([])
        default_offre_emploi_id = (
            http.request.env["tdm.entrevue"]
            .default_get(["offre_emploi_id"])
            .get("offre_emploi_id")
        )
        default_show_jitsi_link = (
            http.request.env["tdm.entrevue"]
            .default_get(["show_jitsi_link"])
            .get("show_jitsi_link")
        )
        stage_id = http.request.env["tdm.entrevue.stage"].search([])
        default_stage_id = (
            http.request.env["tdm.entrevue"]
            .default_get(["stage_id"])
            .get("stage_id")
        )
        default_url_jitsi_employeur = (
            http.request.env["tdm.entrevue"]
            .default_get(["url_jitsi_employeur"])
            .get("url_jitsi_employeur")
        )
        default_url_jitsi_travailleur = (
            http.request.env["tdm.entrevue"]
            .default_get(["url_jitsi_travailleur"])
            .get("url_jitsi_travailleur")
        )
        return http.request.render(
            "tdm.portal_create_tdm_entrevue",
            {
                "name": name,
                "offre_emploi_applique_id": offre_emploi_applique_id,
                "offre_emploi_id": offre_emploi_id,
                "stage_id": stage_id,
                "page_name": "create_tdm_entrevue",
                "default_date_debut_entrevue": default_date_debut_entrevue,
                "default_offre_emploi_applique_id": default_offre_emploi_applique_id,
                "default_offre_emploi_id": default_offre_emploi_id,
                "default_show_jitsi_link": default_show_jitsi_link,
                "default_stage_id": default_stage_id,
                "default_url_jitsi_employeur": default_url_jitsi_employeur,
                "default_url_jitsi_travailleur": default_url_jitsi_travailleur,
            },
        )

    @http.route(
        "/submitted/tdm_entrevue",
        type="http",
        auth="user",
        website=True,
        csrf=True,
    )
    def submit_tdm_entrevue(self, **kw):
        vals = {}

        if kw.get("name"):
            vals["name"] = kw.get("name")

        if kw.get("date_debut_entrevue"):
            vals["date_debut_entrevue"] = kw.get("date_debut_entrevue")

        if (
            kw.get("offre_emploi_applique_id")
            and kw.get("offre_emploi_applique_id").isdigit()
        ):
            vals["offre_emploi_applique_id"] = int(
                kw.get("offre_emploi_applique_id")
            )

        if kw.get("offre_emploi_id") and kw.get("offre_emploi_id").isdigit():
            vals["offre_emploi_id"] = int(kw.get("offre_emploi_id"))

        default_show_jitsi_link = (
            http.request.env["tdm.entrevue"]
            .default_get(["show_jitsi_link"])
            .get("show_jitsi_link")
        )
        if kw.get("show_jitsi_link"):
            vals["show_jitsi_link"] = kw.get("show_jitsi_link") == "True"
        elif default_show_jitsi_link:
            vals["show_jitsi_link"] = False

        if kw.get("stage_id") and kw.get("stage_id").isdigit():
            vals["stage_id"] = int(kw.get("stage_id"))

        if kw.get("url_jitsi_employeur"):
            vals["url_jitsi_employeur"] = kw.get("url_jitsi_employeur")

        if kw.get("url_jitsi_travailleur"):
            vals["url_jitsi_travailleur"] = kw.get("url_jitsi_travailleur")

        new_tdm_entrevue = request.env["tdm.entrevue"].sudo().create(vals)
        return werkzeug.utils.redirect(
            f"/my/tdm_entrevue/{new_tdm_entrevue.id}"
        )

    @http.route(
        "/new/tdm_entrevue_stage", type="http", auth="user", website=True
    )
    def create_new_tdm_entrevue_stage(self, **kw):
        name = http.request.env.user.name
        return http.request.render(
            "tdm.portal_create_tdm_entrevue_stage",
            {"name": name, "page_name": "create_tdm_entrevue_stage"},
        )

    @http.route(
        "/submitted/tdm_entrevue_stage",
        type="http",
        auth="user",
        website=True,
        csrf=True,
    )
    def submit_tdm_entrevue_stage(self, **kw):
        vals = {}

        if kw.get("name"):
            vals["name"] = kw.get("name")

        new_tdm_entrevue_stage = (
            request.env["tdm.entrevue.stage"].sudo().create(vals)
        )
        return werkzeug.utils.redirect(
            f"/my/tdm_entrevue_stage/{new_tdm_entrevue_stage.id}"
        )

    @http.route(
        "/new/tdm_offre_emploi", type="http", auth="user", website=True
    )
    def create_new_tdm_offre_emploi(self, **kw):
        name = http.request.env.user.name
        default_approbation = (
            http.request.env["tdm.offre.emploi"]
            .default_get(["approbation"])
            .get("approbation")
        )
        default_avantage_social = (
            http.request.env["tdm.offre.emploi"]
            .default_get(["avantage_social"])
            .get("avantage_social")
        )
        default_description = (
            http.request.env["tdm.offre.emploi"]
            .default_get(["description"])
            .get("description")
        )
        default_description_entreprise = (
            http.request.env["tdm.offre.emploi"]
            .default_get(["description_entreprise"])
            .get("description_entreprise")
        )
        default_description_sommaire = (
            http.request.env["tdm.offre.emploi"]
            .default_get(["description_sommaire"])
            .get("description_sommaire")
        )
        default_information_supplementaire = (
            http.request.env["tdm.offre.emploi"]
            .default_get(["information_supplementaire"])
            .get("information_supplementaire")
        )
        default_is_temps_pleins = (
            http.request.env["tdm.offre.emploi"]
            .default_get(["is_temps_pleins"])
            .get("is_temps_pleins")
        )
        default_localisation = (
            http.request.env["tdm.offre.emploi"]
            .default_get(["localisation"])
            .get("localisation")
        )
        default_nb_hour_per_week = (
            http.request.env["tdm.offre.emploi"]
            .default_get(["nb_hour_per_week"])
            .get("nb_hour_per_week")
        )
        default_principal_responsabilite = (
            http.request.env["tdm.offre.emploi"]
            .default_get(["principal_responsabilite"])
            .get("principal_responsabilite")
        )
        default_qualification_requise = (
            http.request.env["tdm.offre.emploi"]
            .default_get(["qualification_requise"])
            .get("qualification_requise")
        )
        default_salaire = (
            http.request.env["tdm.offre.emploi"]
            .default_get(["salaire"])
            .get("salaire")
        )
        secteur_activite_ids = http.request.env["tdm.secteur_activite"].search(
            []
        )
        lst_default_secteur_activite_ids = (
            http.request.env["tdm.offre.emploi"]
            .default_get(["secteur_activite_ids"])
            .get("secteur_activite_ids")
        )
        if lst_default_secteur_activite_ids:
            default_secteur_activite_ids = lst_default_secteur_activite_ids[0][
                2
            ]
        else:
            default_secteur_activite_ids = []
        stage_id = http.request.env["tdm.offre.emploi.stage"].search([])
        default_stage_id = (
            http.request.env["tdm.offre.emploi"]
            .default_get(["stage_id"])
            .get("stage_id")
        )
        type_poste_ids = http.request.env["tdm.offre.emploi.type"].search([])
        lst_default_type_poste_ids = (
            http.request.env["tdm.offre.emploi"]
            .default_get(["type_poste_ids"])
            .get("type_poste_ids")
        )
        if lst_default_type_poste_ids:
            default_type_poste_ids = lst_default_type_poste_ids[0][2]
        else:
            default_type_poste_ids = []
        default_website_published = (
            http.request.env["tdm.offre.emploi"]
            .default_get(["website_published"])
            .get("website_published")
        )
        return http.request.render(
            "tdm.portal_create_tdm_offre_emploi",
            {
                "name": name,
                "secteur_activite_ids": secteur_activite_ids,
                "stage_id": stage_id,
                "type_poste_ids": type_poste_ids,
                "page_name": "create_tdm_offre_emploi",
                "default_approbation": default_approbation,
                "default_avantage_social": default_avantage_social,
                "default_description": default_description,
                "default_description_entreprise": default_description_entreprise,
                "default_description_sommaire": default_description_sommaire,
                "default_information_supplementaire": default_information_supplementaire,
                "default_is_temps_pleins": default_is_temps_pleins,
                "default_localisation": default_localisation,
                "default_nb_hour_per_week": default_nb_hour_per_week,
                "default_principal_responsabilite": default_principal_responsabilite,
                "default_qualification_requise": default_qualification_requise,
                "default_salaire": default_salaire,
                "default_secteur_activite_ids": default_secteur_activite_ids,
                "default_stage_id": default_stage_id,
                "default_type_poste_ids": default_type_poste_ids,
                "default_website_published": default_website_published,
            },
        )

    @http.route(
        "/submitted/tdm_offre_emploi",
        type="http",
        auth="user",
        website=True,
        csrf=True,
    )
    def submit_tdm_offre_emploi(self, **kw):
        vals = {}

        if kw.get("name"):
            vals["name"] = kw.get("name")

        default_approbation = (
            http.request.env["tdm.offre.emploi"]
            .default_get(["approbation"])
            .get("approbation")
        )
        if kw.get("approbation"):
            vals["approbation"] = kw.get("approbation") == "True"
        elif default_approbation:
            vals["approbation"] = False

        if kw.get("avantage_social"):
            vals["avantage_social"] = kw.get("avantage_social")

        if kw.get("description"):
            vals["description"] = kw.get("description")

        if kw.get("description_entreprise"):
            vals["description_entreprise"] = kw.get("description_entreprise")

        if kw.get("description_sommaire"):
            vals["description_sommaire"] = kw.get("description_sommaire")

        if kw.get("information_supplementaire"):
            vals["information_supplementaire"] = kw.get(
                "information_supplementaire"
            )

        default_is_temps_pleins = (
            http.request.env["tdm.offre.emploi"]
            .default_get(["is_temps_pleins"])
            .get("is_temps_pleins")
        )
        if kw.get("is_temps_pleins"):
            vals["is_temps_pleins"] = kw.get("is_temps_pleins") == "True"
        elif default_is_temps_pleins:
            vals["is_temps_pleins"] = False

        if kw.get("localisation"):
            vals["localisation"] = kw.get("localisation")

        if kw.get("nb_hour_per_week"):
            nb_hour_per_week_value = kw.get("nb_hour_per_week")
            if nb_hour_per_week_value.replace(".", "", 1).isdigit():
                vals["nb_hour_per_week"] = float(nb_hour_per_week_value)

        if kw.get("principal_responsabilite"):
            vals["principal_responsabilite"] = kw.get(
                "principal_responsabilite"
            )

        if kw.get("qualification_requise"):
            vals["qualification_requise"] = kw.get("qualification_requise")

        if kw.get("salaire"):
            salaire_value = kw.get("salaire")
            if salaire_value.replace(".", "", 1).isdigit():
                vals["salaire"] = float(salaire_value)

        if kw.get("secteur_activite_ids"):
            lst_value_secteur_activite_ids = [
                (4, int(a))
                for a in request.httprequest.form.getlist(
                    "secteur_activite_ids"
                )
            ]
            vals["secteur_activite_ids"] = lst_value_secteur_activite_ids

        if kw.get("stage_id") and kw.get("stage_id").isdigit():
            vals["stage_id"] = int(kw.get("stage_id"))

        if kw.get("type_poste_ids"):
            lst_value_type_poste_ids = [
                (4, int(a))
                for a in request.httprequest.form.getlist("type_poste_ids")
            ]
            vals["type_poste_ids"] = lst_value_type_poste_ids

        default_website_published = (
            http.request.env["tdm.offre.emploi"]
            .default_get(["website_published"])
            .get("website_published")
        )
        if kw.get("website_published"):
            vals["website_published"] = kw.get("website_published") == "True"
        elif default_website_published:
            vals["website_published"] = False

        new_tdm_offre_emploi = (
            request.env["tdm.offre.emploi"].sudo().create(vals)
        )
        return werkzeug.utils.redirect(
            f"/my/tdm_offre_emploi/{new_tdm_offre_emploi.id}"
        )

    @http.route(
        "/new/tdm_offre_emploi_applique",
        type="http",
        auth="user",
        website=True,
    )
    def create_new_tdm_offre_emploi_applique(self, **kw):
        name = http.request.env.user.name
        default_date_application = (
            http.request.env["tdm.offre.emploi.applique"]
            .default_get(["date_application"])
            .get("date_application")
        )
        offre_emploi_id = http.request.env["tdm.offre.emploi"].search([])
        default_offre_emploi_id = (
            http.request.env["tdm.offre.emploi.applique"]
            .default_get(["offre_emploi_id"])
            .get("offre_emploi_id")
        )
        stage_id = http.request.env["tdm.offre.emploi.applique.stage"].search(
            []
        )
        default_stage_id = (
            http.request.env["tdm.offre.emploi.applique"]
            .default_get(["stage_id"])
            .get("stage_id")
        )
        return http.request.render(
            "tdm.portal_create_tdm_offre_emploi_applique",
            {
                "name": name,
                "offre_emploi_id": offre_emploi_id,
                "stage_id": stage_id,
                "page_name": "create_tdm_offre_emploi_applique",
                "default_date_application": default_date_application,
                "default_offre_emploi_id": default_offre_emploi_id,
                "default_stage_id": default_stage_id,
            },
        )

    @http.route(
        "/submitted/tdm_offre_emploi_applique",
        type="http",
        auth="user",
        website=True,
        csrf=True,
    )
    def submit_tdm_offre_emploi_applique(self, **kw):
        vals = {}

        if kw.get("name"):
            vals["name"] = kw.get("name")

        if kw.get("date_application"):
            vals["date_application"] = kw.get("date_application")

        if kw.get("offre_emploi_id") and kw.get("offre_emploi_id").isdigit():
            vals["offre_emploi_id"] = int(kw.get("offre_emploi_id"))

        if kw.get("stage_id") and kw.get("stage_id").isdigit():
            vals["stage_id"] = int(kw.get("stage_id"))

        new_tdm_offre_emploi_applique = (
            request.env["tdm.offre.emploi.applique"].sudo().create(vals)
        )
        return werkzeug.utils.redirect(
            f"/my/tdm_offre_emploi_applique/{new_tdm_offre_emploi_applique.id}"
        )

    @http.route(
        "/new/tdm_offre_emploi_applique_stage",
        type="http",
        auth="user",
        website=True,
    )
    def create_new_tdm_offre_emploi_applique_stage(self, **kw):
        name = http.request.env.user.name
        return http.request.render(
            "tdm.portal_create_tdm_offre_emploi_applique_stage",
            {
                "name": name,
                "page_name": "create_tdm_offre_emploi_applique_stage",
            },
        )

    @http.route(
        "/submitted/tdm_offre_emploi_applique_stage",
        type="http",
        auth="user",
        website=True,
        csrf=True,
    )
    def submit_tdm_offre_emploi_applique_stage(self, **kw):
        vals = {}

        if kw.get("name"):
            vals["name"] = kw.get("name")

        new_tdm_offre_emploi_applique_stage = (
            request.env["tdm.offre.emploi.applique.stage"].sudo().create(vals)
        )
        return werkzeug.utils.redirect(
            f"/my/tdm_offre_emploi_applique_stage/{new_tdm_offre_emploi_applique_stage.id}"
        )

    @http.route(
        "/new/tdm_offre_emploi_stage", type="http", auth="user", website=True
    )
    def create_new_tdm_offre_emploi_stage(self, **kw):
        name = http.request.env.user.name
        return http.request.render(
            "tdm.portal_create_tdm_offre_emploi_stage",
            {"name": name, "page_name": "create_tdm_offre_emploi_stage"},
        )

    @http.route(
        "/submitted/tdm_offre_emploi_stage",
        type="http",
        auth="user",
        website=True,
        csrf=True,
    )
    def submit_tdm_offre_emploi_stage(self, **kw):
        vals = {}

        if kw.get("name"):
            vals["name"] = kw.get("name")

        new_tdm_offre_emploi_stage = (
            request.env["tdm.offre.emploi.stage"].sudo().create(vals)
        )
        return werkzeug.utils.redirect(
            f"/my/tdm_offre_emploi_stage/{new_tdm_offre_emploi_stage.id}"
        )

    @http.route(
        "/new/tdm_offre_emploi_type", type="http", auth="user", website=True
    )
    def create_new_tdm_offre_emploi_type(self, **kw):
        name = http.request.env.user.name
        return http.request.render(
            "tdm.portal_create_tdm_offre_emploi_type",
            {"name": name, "page_name": "create_tdm_offre_emploi_type"},
        )

    @http.route(
        "/submitted/tdm_offre_emploi_type",
        type="http",
        auth="user",
        website=True,
        csrf=True,
    )
    def submit_tdm_offre_emploi_type(self, **kw):
        vals = {}

        if kw.get("name"):
            vals["name"] = kw.get("name")

        new_tdm_offre_emploi_type = (
            request.env["tdm.offre.emploi.type"].sudo().create(vals)
        )
        return werkzeug.utils.redirect(
            f"/my/tdm_offre_emploi_type/{new_tdm_offre_emploi_type.id}"
        )

    @http.route(
        "/new/tdm_secteur_activite", type="http", auth="user", website=True
    )
    def create_new_tdm_secteur_activite(self, **kw):
        name = http.request.env.user.name
        return http.request.render(
            "tdm.portal_create_tdm_secteur_activite",
            {"name": name, "page_name": "create_tdm_secteur_activite"},
        )

    @http.route(
        "/submitted/tdm_secteur_activite",
        type="http",
        auth="user",
        website=True,
        csrf=True,
    )
    def submit_tdm_secteur_activite(self, **kw):
        vals = {}

        if kw.get("name"):
            vals["name"] = kw.get("name")

        new_tdm_secteur_activite = (
            request.env["tdm.secteur_activite"].sudo().create(vals)
        )
        return werkzeug.utils.redirect(
            f"/my/tdm_secteur_activite/{new_tdm_secteur_activite.id}"
        )
