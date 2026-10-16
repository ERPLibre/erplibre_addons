# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import fields, models


class DevopsRequirementCategory(models.Model):
    """Domaine fonctionnel d'un requis (CRM, inventaire, reporting...).

    Les domaines sont propres au projet : le module n'en livre aucun.
    """

    _name = "devops.requirement.category"
    _inherit = "devops.requirement.classifier"
    _description = "Requirement domain"

    requirement_ids = fields.One2many(
        "devops.requirement", "category_id", string="Requirements"
    )
