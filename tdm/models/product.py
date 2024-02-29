from odoo import api, fields, models


class Product(models.Model):
    _inherit = "product.template"

    is_feature_travailleur_libre = fields.Boolean(
        help="Forfait travailleur libre",
        track_visibility="onchange",
    )

    is_feature_entreprise_bronze = fields.Boolean(
        help="Forfait entreprise bronze",
        track_visibility="onchange",
    )

    is_feature_entreprise_argent = fields.Boolean(
        help="Forfait entreprise argent",
        track_visibility="onchange",
    )

    is_feature_entreprise_or = fields.Boolean(
        help="Forfait entreprise or",
        track_visibility="onchange",
    )
