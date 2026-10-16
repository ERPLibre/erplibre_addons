# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import fields, models


class DevopsGuideSection(models.Model):
    """Une section d'une page, dont la FORME tient dans `kind`.

    `lead` rend son `intro` comme corps de texte ; `cards` rend ses cartes
    en grille ; `roadmap` les rend en étapes numérotées. Une étape de
    feuille de route est donc une carte sans bouton, et une phase une
    section portant un numéro — d'où un seul modèle de carte pour les
    trois formes.
    """

    _name = "devops.guide.section"
    _description = "Guide section"
    _order = "sequence, id"

    guide_id = fields.Many2one(
        "devops.guide",
        string="Guide",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10)
    kind = fields.Selection(
        [
            ("lead", "Lead text"),
            ("cards", "Card grid"),
            ("roadmap", "Roadmap"),
        ],
        string="Shape",
        required=True,
        default="cards",
    )
    # Numéro affiché en pastille devant le titre, pour une phase.
    num = fields.Char(string="Number")
    title = fields.Char(string="Title", translate=True)
    # Html et non Text : un texte d'introduction porte de la mise en forme
    # en ligne, qu'un champ Text perdrait.
    intro = fields.Html(string="Intro", translate=True, sanitize=True)
    card_ids = fields.One2many(
        "devops.guide.card", "section_id", string="Cards"
    )
