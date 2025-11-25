from odoo import models, fields


class Aliment(models.Model):
    _name = 'aliment.aliment'
    _description = 'Aliment'

    name = fields.Char(string='Nom', required=True)
