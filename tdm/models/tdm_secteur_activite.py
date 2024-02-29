from odoo import _, api, fields, models


class TdmSecteurActivite(models.Model):
    _name = "tdm.secteur_activite"
    _description = "tdm_secteur_activite"
    _order = "name, id"

    name = fields.Char()
