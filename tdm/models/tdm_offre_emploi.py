from odoo import _, api, fields, models


class TdmOffreEmploi(models.Model):
    _name = "tdm.offre.emploi"
    _inherit = ["portal.mixin", "mail.activity.mixin", "mail.thread"]
    _description = "Offre d'emploi"

    name = fields.Char(
        string="Titre",
        track_visibility="onchange",
    )

    active = fields.Boolean(
        string="Actif",
        track_visibility="onchange",
        default=True,
    )

    stage_id = fields.Many2one(
        comodel_name="tdm.offre.emploi.stage",
        string="Stage",
        default=lambda s: s.default_stage_id(),
        track_visibility="onchange",
    )

    evaluation_id = fields.Many2one(
        comodel_name="survey.survey",
        string="Évaluation",
        track_visibility="onchange",
    )

    category_id = fields.Many2one(
        comodel_name="tdm.offre.emploi.category",
        string="Catégorie",
        track_visibility="onchange",
    )

    tag_ids = fields.Many2many(
        comodel_name="tdm.offre.emploi.tag",
        string="Étiquette",
        track_visibility="onchange",
    )

    type_poste_ids = fields.Many2many(
        comodel_name="tdm.offre.emploi.type",
        string="Type de postes",
        track_visibility="onchange",
    )

    secteur_activite_ids = fields.Many2many(
        comodel_name="tdm.secteur_activite",
        string="Secteur d'activité",
        track_visibility="onchange",
    )

    approbation = fields.Boolean(
        help=(
            "N'a pas encore d'utilité, mais l'admin confirme cet offre"
            " d'emploi."
        ),
        track_visibility="onchange",
    )

    # TODO approbation_date readonly (action write or action create, update date if approbation is True)

    website_published = fields.Boolean(
        track_visibility="onchange",
    )

    is_temps_pleins = fields.Boolean(
        string="Est temps pleins",
        help="Si faux, c'est temps partiel.",
        track_visibility="onchange",
    )

    nb_hour_per_week = fields.Integer(
        string="Nombre d'heure par semaine",
        track_visibility="onchange",
    )

    description_entreprise = fields.Html(
        string="Description de l'entreprise",
        related="partner_employeur_id.description",
        store=True,
        track_visibility="onchange",
    )

    description = fields.Html(
        string="Description",
        help="Description du poste",
        track_visibility="onchange",
    )

    principal_responsabilite = fields.Html(
        string="Principal responsabilité",
        track_visibility="onchange",
    )

    qualification_requise = fields.Html(
        string="Qualification requise",
        track_visibility="onchange",
    )

    information_supplementaire = fields.Html(
        string="Information supplémentaire",
        track_visibility="onchange",
    )

    localisation = fields.Char(
        track_visibility="onchange",
    )

    salaire = fields.Float(
        track_visibility="onchange",
    )

    avantage_social = fields.Html(
        track_visibility="onchange",
    )

    partner_employeur_id = fields.Many2one(
        comodel_name="res.partner",
        string="Société",
        track_visibility="onchange",
        domain=[("est_employeur", "=", True)],
    )

    # TODO offre_emploi_applique_ids : o2m

    def _compute_access_url(self):
        super(TdmOffreEmploi, self)._compute_access_url()
        for tdm_offre_emploi in self:
            tdm_offre_emploi.access_url = (
                "/my/tdm_offre_emploi/%s" % tdm_offre_emploi.id
            )

    @api.model
    def default_stage_id(self):
        stage_id = self.env["tdm.offre.emploi.stage"].search(
            [("is_init", "=", True)], limit=1
        )
        if not stage_id:
            # Take first one
            stage_id = self.env["tdm.offre.emploi.stage"].search([], limit=1)
        return stage_id
