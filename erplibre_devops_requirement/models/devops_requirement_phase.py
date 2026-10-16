# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import fields, models


class DevopsRequirementPhase(models.Model):
    """Jalon de livraison d'un requis (preuve de concept, phase 1, bascule...).

    Les jalons sont propres au projet : le module n'en livre aucun.
    """

    _name = "devops.requirement.phase"
    _inherit = "devops.requirement.classifier"
    _description = "Requirement phase"

    requirement_ids = fields.One2many(
        "devops.requirement", "phase_id", string="Requirements"
    )
