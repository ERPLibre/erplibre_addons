from odoo import _, api, fields, models


class TdmOffreEmploiCategory(models.Model):
    _name = "tdm.offre.emploi.category"
    _description = "tdm_offre_emploi_category"
    _order = "name, id"

    name = fields.Char()
