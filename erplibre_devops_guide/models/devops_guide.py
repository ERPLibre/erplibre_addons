# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import api, fields, models


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
    tour_name = fields.Char(
        string="Tour name",
        help=(
            "Technical name of a registered tour. Left empty, or with "
            "web_tour absent, the tour button is not shown."
        ),
    )
    tour_label = fields.Char(string="Tour button", translate=True)
    # Identifiant XML ouvert par le second bouton du héros.
    primary_action = fields.Char(
        string="Primary action",
        help="XML id of the action the second hero button opens.",
    )
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

    def _resolve_from_context(self):
        """Rend le guide désigné par le contexte, ou un recordset vide.

        `guide_xmlid` sert aux pages posées en données par un projet ;
        `guide_id` sert au bouton Preview du formulaire, qui n'a pas
        d'identifiant XML sous la main. Un identifiant inconnu rend vide
        plutôt que de lever : l'écran s'ouvre et dit qu'il n'y a rien.
        """
        xmlid = self.env.context.get("guide_xmlid")
        if xmlid:
            # `env.ref` rend l'enregistrement de N'IMPORTE quel modèle : un
            # `guide_xmlid` qui désigne une vue ou une action rendrait un
            # recordset étranger, dont `get_page` échouerait sur un champ
            # inconnu. Vérifier le modèle avant de le rendre.
            found = self.env.ref(xmlid, raise_if_not_found=False)
            if found and found._name == self._name:
                return found
            return self.browse()
        guide_id = self.env.context.get("guide_id")
        if guide_id:
            return self.browse(guide_id).exists()
        return self.browse()

    @api.model
    def get_page_from_context(self):
        """Point d'entrée du composant : un appel, une page ou rien.

        Rend `{}` quand le contexte ne désigne aucun guide ou qu'il en
        désigne un disparu, ce que le composant affiche comme une page
        vide plutôt qu'en cassant l'écran.
        """
        guide = self._resolve_from_context()
        return guide.get_page() if guide else {}

    def get_page(self):
        """Rend la page entière en un seul aller-retour.

        Chaque valeur passe par `or ""` : un Char, un Text, un Html ou un
        Many2one vide se relit False côté Python, et un False rendu au
        navigateur s'affiche « false » dans la page.
        """
        self.ensure_one()
        return {
            "id": self.id,
            "eyebrow": self.eyebrow or "",
            "title": self.title or "",
            "subtitle": self.subtitle or "",
            "tour_name": self.tour_name or "",
            "tour_label": self.tour_label or "",
            "primary_action": self.primary_action or "",
            "primary_label": self.primary_label or "",
            "footer": self.footer or "",
            "footer_small": self.footer_small or "",
            "stats": [
                {
                    "value": stat.value or "",
                    "label": stat.label or "",
                    "action_xmlid": stat.action_xmlid or "",
                }
                for stat in self.stat_ids
            ],
            "sections": [
                {
                    "kind": section.kind,
                    "num": section.num or "",
                    "title": section.title or "",
                    "intro": section.intro or "",
                    "cards": [
                        {
                            "num": card.num or "",
                            "icon": card.icon or "",
                            "title": card.title or "",
                            "badge": card.badge or "",
                            "problem": card.problem or "",
                            "solution": card.solution or "",
                            "action_xmlid": card.action_xmlid or "",
                            "url": card.url or "",
                            "action_label": card.resolved_label or "",
                            "count_model": card.count_model or "",
                            "count_domain": card._json_domain(),
                        }
                        for card in section.card_ids
                    ],
                }
                for section in self.section_ids
            ],
        }

    def action_preview(self):
        """Ouvre la page depuis son formulaire.

        C'est ce qui permet de voir un guide sans qu'un projet ait créé
        son propre `ir.actions.client` : le module n'en livre aucun.
        """
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "devops_guide.page",
            "name": self.title or self.name,
            "context": {"guide_id": self.id},
        }
