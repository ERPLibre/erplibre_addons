# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import fields, models


class DevopsRequirement(models.Model):
    """Requis logiciel d'un projet d'implémentation, classé en MoSCoW.

    Le niveau MoSCoW dit ce à quoi le projet s'engage ; `priority` ordonne
    le travail À L'INTÉRIEUR d'un niveau. Les trois booléens suivent le
    cycle : le client ACCEPTE le requis, l'APPROUVE pour développement,
    puis sa réalisation est constatée.
    """

    _name = "devops.requirement"
    _description = "Software requirement (MoSCoW)"
    _order = "category_id, sequence, code"

    code = fields.Char(string="Code", index=True)
    name = fields.Char(string="Requirement", required=True, translate=True)
    category_id = fields.Many2one(
        "devops.requirement.category",
        string="Domain",
        required=True,
        index=True,
        ondelete="restrict",
    )
    moscow = fields.Selection(
        [
            ("must", "Must have"),
            ("should", "Should have"),
            ("could", "Could have"),
            ("wont", "Won't have"),
        ],
        string="MoSCoW level",
        default="should",
        index=True,
    )
    priority = fields.Selection(
        [("high", "High"), ("medium", "Medium"), ("low", "Low")],
        string="Priority",
        default="medium",
        index=True,
    )
    phase_id = fields.Many2one(
        "devops.requirement.phase",
        string="Phase",
        index=True,
        ondelete="restrict",
    )
    size = fields.Selection(
        [("s", "Small"), ("m", "Medium"), ("l", "Large")],
        string="Estimated effort",
    )
    responsible_id = fields.Many2one("res.users", string="Responsible")
    description = fields.Text(string="Description", translate=True)
    notes = fields.Text(string="Notes")
    sequence = fields.Integer(default=10)
    accepted = fields.Boolean(string="Accepted", index=True)
    approved = fields.Boolean(string="Approved", index=True)
    done = fields.Boolean(string="Done", index=True)
    # Comment le requis est couvert — module, menu, vue — ou, s'il ne l'est
    # pas encore, l'état actuel et la suite.
    achievement = fields.Text(string="Achievement")
    # Ce qui manque encore pour une couverture complète en production :
    # dépendance amont, décision du client, intégration externe.
    missing = fields.Text(string="What is missing")
