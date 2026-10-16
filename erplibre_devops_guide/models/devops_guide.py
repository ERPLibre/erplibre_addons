# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import fields, models


class DevopsGuide(models.Model):
    """Page de présentation d'un projet, décrite en données.

    Le module ne livre aucune page : un projet crée la sienne et une
    action cliente l'ouvre en passant `guide_xmlid` ou `guide_id` au
    contexte. Plusieurs pages coexistent dans une base.
    """

    _name = "devops.guide"
    _description = "Presentation guide"
    _order = "name"

    name = fields.Char(string="Internal name", required=True)
    eyebrow = fields.Char(string="Eyebrow", translate=True)
    title = fields.Char(string="Title", required=True, translate=True)
    subtitle = fields.Text(string="Subtitle", translate=True)
    # Visite guidée lancée par le premier bouton du héros. Vide : pas de
    # bouton — toutes les pages n'ont pas de visite.
    tour_name = fields.Char(string="Tour name")
    tour_label = fields.Char(string="Tour button", translate=True)
    # Identifiant XML ouvert par le second bouton du héros.
    primary_action = fields.Char(string="Primary action")
    primary_label = fields.Char(string="Primary button", translate=True)
    footer = fields.Text(string="Footer", translate=True)
    footer_small = fields.Char(string="Footer note", translate=True)
    active = fields.Boolean(default=True)
    section_ids = fields.One2many(
        "devops.guide.section", "guide_id", string="Sections"
    )
    stat_ids = fields.One2many(
        "devops.guide.stat", "guide_id", string="Statistics"
    )
