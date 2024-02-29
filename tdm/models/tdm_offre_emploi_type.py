from odoo import _, api, fields, models


class TdmOffreEmploiType(models.Model):
    _name = "tdm.offre.emploi.type"
    _description = "tdm_offre_emploi_type"
    _order = "name, id"

    name = fields.Char()
