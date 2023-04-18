from odoo import http, models, fields, api, exceptions

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
    def website_cv_get(self):
        contact_reponse = http.request.env['website.cv'].search([], limit=1)
        contacts = list()
        for contact in contact_reponse:
            contacts.append({
                "id": contact["id"],
                "name": contact["name"],
                "address": contact["address"],
                "phone": contact["phone"],
                "email": contact["email"],
                "description": contact["description"],

                "name_experience": contact["name_experience"],
                "entreprise_name_experience": contact["entreprise_name_experience"],
                "description_experience": contact["description_experience"],
                "date_experience": contact["date_experience"],

                "name_projets": contact["name_projets"],
                "entreprise_name_projets": contact["entreprise_name_projets"],
                "description_projets": contact["description_projets"],
                "date_projets": contact["date_projets"],

                "name_formations": contact["name_formations"],
                "entreprise_name_formations": contact["entreprise_name_formations"],
                "description_formations": contact["description_formations"],
                "date_formations": contact["date_formations"]
            })
        return contacts
