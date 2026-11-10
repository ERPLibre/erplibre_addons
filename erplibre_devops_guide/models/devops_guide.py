# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from collections import defaultdict

from odoo import _, api, fields, models


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
    # Visite guidée lancée par le premier bouton du héros. Vide, ou absente
    # du registre JS des visites : pas de bouton — toutes les pages n'ont
    # pas de visite, et un bouton qui ne lance rien n'est pas montré.
    tour_name = fields.Char(
        string="Tour name",
        help=(
            "Technical name of a registered tour. Left empty, or unknown to "
            "the tour registry of the web client, the tour button is not "
            "shown."
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
        navigateur s'affiche « false ». Une carte réservée à des groupes
        dont l'utilisateur n'est pas membre n'est pas rendue : la règle
        d'accès des cartes en décide. Les cartes viennent d'une recherche
        et non de `card_ids` : le cache d'un One2many est partagé par les
        environnements d'une transaction, et une valeur lue par un autre
        utilisateur, ou en sudo, ne refléterait pas les droits du lecteur.
        """
        self.ensure_one()
        cards_by_section = defaultdict(list)
        for card in self.env["devops.guide.card"].search(
            [("section_id", "in", self.section_ids.ids)]
        ):
            cards_by_section[card.section_id.id].append(card)
        return {
            "id": self.id,
            "eyebrow": self.eyebrow or "",
            "title": self.title or "",
            "subtitle": self.subtitle or "",
            "tour_name": self.tour_name or "",
            # Le repli est traduit ici, côté serveur : une chaîne écrite en
            # dur dans une expression du gabarit n'est jamais extraite.
            "tour_label": self.tour_label or _("Start the tour"),
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
                        card._get_page_card()
                        for card in cards_by_section[section.id]
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
