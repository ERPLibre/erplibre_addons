# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import _, api, fields, models

# Clés du requis rendues par carte. Une carte sans requis rend ces mêmes
# clés, vides : le gabarit lit `card.requirement.code` sans tester
# l'existence du dictionnaire.
REQUIREMENT_KEYS = (
    "id",
    "code",
    "name",
    "moscow",
    "moscow_label",
    "test_state",
    "test_state_label",
    "has_guide",
)


class DevopsGuideCard(models.Model):
    """Une carte : un problème, sa réponse, et au plus un bouton.

    Le bouton se résout dans cet ordre — `url` ouvre un onglet,
    `action_xmlid` appelle l'action, `count_model` ouvre ce modèle filtré
    par `count_domain`. Les trois vides : aucun bouton, ce qui rend une
    étape de feuille de route.

    `action_label` accepte le marqueur `{count}`, remplacé par le décompte
    quand `count_model` est posé. Un libellé reste ainsi juste quand les
    données bougent, là où un nombre écrit en dur dérive.

    Le libellé fait partie du contrat : une cible sans libellé ne rend
    aucun bouton, plutôt qu'un bouton vide ne portant que sa flèche.

    `requirement_id` rattache la carte à un requis : la page affiche alors
    son code, son niveau MoSCoW et l'état de ses tests, et la carte lance
    la visite guidée du requis. `tour_name` posé sur la carte l'emporte sur
    celle du requis (`effective_tour_name`).

    `groups_id` restreint la carte : vide, tout lecteur du guide la voit ;
    posé, seul un membre d'au moins un de ces groupes la voit. C'est ce qui
    évite de montrer une visite qui mène vers un menu que le lecteur ne
    peut pas ouvrir. La restriction est une règle d'accès
    (security/devops_guide_security.xml) : elle vaut pour la page, pour
    l'onglet Guide du requis et pour un appel RPC.
    """

    _name = "devops.guide.card"
    _inherit = "devops.guide.counter.mixin"
    _description = "Guide card"
    _order = "sequence, id"

    section_id = fields.Many2one(
        "devops.guide.section",
        string="Section",
        required=True,
        ondelete="cascade",
        index=True,
    )
    # La section n'a pas de nom : c'est la page qui dit, vue d'un requis,
    # où la carte est présentée.
    guide_id = fields.Many2one(
        related="section_id.guide_id", string="Guide", store=False
    )
    sequence = fields.Integer(default=10)
    # Numéro de l'étape, pour une section en feuille de route.
    num = fields.Char(string="Number")
    icon = fields.Char(
        string="Icon",
        help="Font Awesome class without the fa prefix, e.g. fa-database.",
    )
    title = fields.Char(string="Title", translate=True)
    # Mention courte posée à côté du titre, pour distinguer une carte des
    # autres sans toucher à son texte.
    badge = fields.Char(string="Badge", translate=True)
    problem = fields.Text(string="Problem", translate=True)
    solution = fields.Text(string="Solution", translate=True)
    action_xmlid = fields.Char(
        string="Action",
        help="XML id of an action, e.g. crm.crm_lead_action_pipeline.",
    )
    url = fields.Char(
        string="URL",
        help="Opened in a new tab, and takes precedence over the action.",
    )
    action_label = fields.Char(
        string="Button label",
        translate=True,
        help=(
            "The marker {count} is replaced by the counted figure when a "
            "counted model is set, so the label stays true as data changes. "
            "Without a counted model the marker is left as written."
        ),
    )
    resolved_label = fields.Char(
        string="Resolved label", compute="_compute_resolved_label"
    )
    requirement_id = fields.Many2one(
        "devops.requirement",
        string="Requirement",
        ondelete="set null",
        index=True,
        help="The card shows this requirement's code, level and test state.",
    )
    tour_name = fields.Char(
        string="Tour name",
        help=(
            "Technical name of a registered tour. Left empty, the card "
            "launches the tour of its requirement, if any."
        ),
    )
    tour_label = fields.Char(string="Tour button", translate=True)
    effective_tour_name = fields.Char(
        string="Effective tour", compute="_compute_effective_tour_name"
    )
    groups_id = fields.Many2many(
        "res.groups",
        "devops_guide_card_res_groups_rel",
        "card_id",
        "group_id",
        string="Groups",
        help=(
            "Left empty, every reader of the guide sees the card. Otherwise "
            "only members of at least one of these groups see it."
        ),
    )

    @api.constrains("section_id")
    def _check_section_renders_cards(self):
        for rec in self:
            rec.section_id._check_lead_has_no_cards()

    @api.depends("tour_name", "requirement_id.tour_name")
    @api.depends_context("uid")
    def _compute_effective_tour_name(self):
        """Rend la visite de la carte, sinon celle du requis, sinon "".

        La visite du requis n'est lue que si l'utilisateur peut lire le
        requis : sinon la lecture lèverait AccessError et ferait échouer
        toute la page, les cartes étant calculées ensemble. La valeur
        dépend donc de l'utilisateur, d'où `depends_context("uid")`. "" et
        non False : la valeur part telle quelle vers la page.
        """
        for rec in self:
            requirement = rec.requirement_id
            requirement_tour = (
                requirement.tour_name
                if requirement and requirement.has_access("read")
                else ""
            )
            rec.effective_tour_name = rec.tour_name or requirement_tour or ""

    @api.depends("action_label", "count_model", "count_domain")
    def _compute_resolved_label(self):
        for rec in self:
            label = rec.action_label or ""
            if rec.count_model and "{count}" in label:
                count = rec._count_records(rec.count_model, rec.count_domain)
                label = label.replace("{count}", str(count))
            rec.resolved_label = label

    def _target_is_reachable(self):
        """Dit si l'utilisateur courant peut ouvrir la cible du bouton.

        La cible suit l'ordre du bouton : une `url` est toujours tenue pour
        ouvrable ; une action l'est si elle existe, que l'utilisateur est
        membre d'un de ses `groups_id` (s'il y en a) et qu'il peut lire son
        `res_model` (s'il y en a un) ; un modèle compté l'est s'il existe
        et que l'utilisateur peut le lire. Sans cible, rien à ouvrir : True.

        Les métadonnées de l'action se lisent en sudo, les droits se
        vérifient avec l'environnement de l'appelant.
        """
        self.ensure_one()
        if self.url:
            return True
        if self.action_xmlid:
            try:
                action = self.env.ref(
                    self.action_xmlid, raise_if_not_found=False
                )
            except ValueError:
                # Identifiant sans module (« action » au lieu de
                # « module.action ») : `env.ref` le refuse en levant.
                action = None
            if not action or not action._name.startswith("ir.actions."):
                return False
            action = action.sudo()
            groups = (
                action.groups_id if "groups_id" in action._fields else None
            )
            if groups and not (groups & self.env.user.groups_id):
                return False
            res_model = (
                action.res_model if "res_model" in action._fields else False
            )
            if res_model:
                return res_model in self.env and self.env[
                    res_model
                ].has_access("read")
            return True
        if self.count_model:
            return self.count_model in self.env and self.env[
                self.count_model
            ].has_access("read")
        return True

    def _get_page_requirement(self):
        """Rend le requis de la carte pour la page, sans un seul False.

        Une carte sans requis, ou dont le requis n'est pas lisible par
        l'utilisateur, rend les clés de REQUIREMENT_KEYS vides. `has_guide`
        vaut True ou "" : un booléen faux s'afficherait « false » s'il
        était un jour écrit dans le gabarit, comme toute autre valeur.
        """
        self.ensure_one()
        requirement = self.requirement_id
        if not requirement or not requirement.has_access("read"):
            return dict.fromkeys(REQUIREMENT_KEYS, "")
        moscow_labels = dict(
            requirement._fields["moscow"]._description_selection(self.env)
        )
        state_labels = dict(
            requirement._fields["test_state"]._description_selection(self.env)
        )
        return {
            "id": requirement.id,
            "code": requirement.code or "",
            "name": requirement.name or "",
            "moscow": requirement.moscow or "",
            "moscow_label": moscow_labels.get(requirement.moscow, ""),
            "test_state": requirement.test_state or "",
            "test_state_label": state_labels.get(requirement.test_state, ""),
            "has_guide": True if requirement.guide_id else "",
        }

    def _get_page_card(self):
        """Rend la carte pour `get_page`.

        Un bouton dont la cible n'est pas ouvrable par l'utilisateur est
        retiré : `action_xmlid` et `action_label` sont rendus vides, et le
        gabarit, qui exige un libellé, n'affiche aucun bouton. Vider aussi
        le libellé empêche le repli sur `count_model`, qui ouvrirait une
        autre cible que celle annoncée.
        """
        self.ensure_one()
        reachable = self._target_is_reachable()
        return {
            "num": self.num or "",
            "icon": self.icon or "",
            "title": self.title or "",
            "badge": self.badge or "",
            "problem": self.problem or "",
            "solution": self.solution or "",
            "action_xmlid": (self.action_xmlid or "") if reachable else "",
            "url": self.url or "",
            "action_label": (self.resolved_label or "") if reachable else "",
            "count_model": self.count_model or "",
            "count_domain": self._json_domain(),
            "tour_name": self.effective_tour_name or "",
            # Repli traduit côté serveur, dans la langue du lecteur.
            "tour_label": self.tour_label or _("Show me"),
            "requirement": self._get_page_requirement(),
        }
