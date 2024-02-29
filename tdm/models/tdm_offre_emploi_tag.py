from odoo import _, api, fields, models


class TdmOffreEmploiTag(models.Model):
    _name = "tdm.offre.emploi.tag"
    _description = "tdm_offre_emploi_tag"
    _order = "name, id"

    name = fields.Char()
