# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import fields, models


class DevopsRequirementClassifier(models.AbstractModel):
    """Axe de classement d'un requis : un code stable et un libellé.

    Le code est l'identifiant employé par les données d'un projet et par
    les domaines des décomptes ; il est unique et ne se traduit pas. Le
    libellé se traduit.
    """

    _name = "devops.requirement.classifier"
    _description = "Requirement classification axis"
    _order = "sequence, code"

    code = fields.Char(string="Code", required=True, index=True)
    name = fields.Char(string="Name", required=True, translate=True)
    sequence = fields.Integer(default=10)

    _sql_constraints = [
        ("code_uniq", "unique(code)", "The code must be unique."),
    ]
