# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import fields, models


class DevopsRequirementThreat(models.Model):
    """Menace qui pèse sur un requis, classée selon STRIDE.

    Une ligne par menace : un requis en porte souvent plusieurs, chacune
    avec sa mitigation et le risque qui reste une fois celle-ci en place.
    """

    _name = "devops.requirement.threat"
    _description = "Requirement threat (STRIDE)"
    _order = "requirement_id, sequence, id"

    requirement_id = fields.Many2one(
        "devops.requirement",
        string="Requirement",
        required=True,
        index=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(default=10)
    stride = fields.Selection(
        [
            ("spoofing", "Spoofing"),
            ("tampering", "Tampering"),
            ("repudiation", "Repudiation"),
            ("information_disclosure", "Information disclosure"),
            ("denial_of_service", "Denial of service"),
            ("elevation_of_privilege", "Elevation of privilege"),
        ],
        string="STRIDE category",
        required=True,
    )
    description = fields.Text(string="Threat", translate=True)
    mitigation = fields.Text(string="Mitigation", translate=True)
    # Chaque libellé porte le mot « risk » : « High » et « Low » sont déjà
    # ceux de `priority`, « Normal » et « Medium » ceux de `priority` et de
    # `size`. Un même terme anglais sur deux axes ne fait qu'une entrée de
    # traduction, impossible à accorder dans une langue genrée (une
    # priorité « haute », un risque « élevé »).
    residual_risk = fields.Selection(
        [
            ("low", "Low risk"),
            ("moderate", "Moderate risk"),
            ("high", "High risk"),
        ],
        string="Residual risk",
    )
