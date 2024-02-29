from odoo import _, api, fields, models


class Partner(models.Model):
    _inherit = "res.partner"

    est_travailleur = fields.Boolean(
        store=True,
        compute="_compute_is_feature",
        track_visibility="onchange",
    )

    est_employeur = fields.Boolean(
        store=True,
        compute="_compute_is_feature",
        track_visibility="onchange",
    )

    is_feature_travailleur_libre = fields.Boolean(
        store=True,
        compute="_compute_is_feature",
        help="Forfait travailleur libre",
        track_visibility="onchange",
    )

    is_feature_entreprise_bronze = fields.Boolean(
        store=True,
        compute="_compute_is_feature",
        help="Forfait entreprise bronze",
        track_visibility="onchange",
    )

    is_feature_entreprise_argent = fields.Boolean(
        store=True,
        compute="_compute_is_feature",
        help="Forfait entreprise argent. Montre le lien Jitsi en entrevue.",
        track_visibility="onchange",
    )

    is_feature_entreprise_or = fields.Boolean(
        store=True,
        compute="_compute_is_feature",
        help="Forfait entreprise or.  Montre le lien Jitsi en entrevue.",
        track_visibility="onchange",
    )

    stage_travailleur_id = fields.Many2one(
        comodel_name="tdm.travailleur.stage",
        string="Stage travailleur",
        default=lambda s: s.default_stage_travailleur_id(),
        track_visibility="onchange",
    )

    description = fields.Html(
        help=(
            "Description de l'employeur ou du travailleur, sera affiché sur"
            " les offres d'emploi ou les profils."
        ),
        track_visibility="onchange",
    )

    secteur_activite_ids = fields.Many2many(
        comodel_name="tdm.secteur_activite",
        string="Secteur d'activités",
        track_visibility="onchange",
    )

    preference_category_ids = fields.Many2many(
        comodel_name="tdm.offre.emploi.category",
        string="Préférence de catégorie",
        track_visibility="onchange",
    )

    preference_type_ids = fields.Many2many(
        comodel_name="tdm.offre.emploi.type",
        string="Préférence de type",
        track_visibility="onchange",
    )

    resume_fr = fields.Many2one(
        string="Résumé FR",
        comodel_name="ir.attachment",
        domain="[('res_model', '=', 'res.partner'), ('res_id', '=', id)]",
        track_visibility="onchange",
        help="Téléverser un fichier résumé en Français.",
    )

    resume_en = fields.Many2one(
        string="Résumé EN",
        comodel_name="ir.attachment",
        domain="[('res_model', '=', 'res.partner'), ('res_id', '=', id)]",
        track_visibility="onchange",
        help="Téléverser un fichier résumé en Anglais.",
    )

    cv_fr = fields.Many2one(
        string="CV FR",
        comodel_name="ir.attachment",
        domain="[('res_model', '=', 'res.partner'), ('res_id', '=', id)]",
        track_visibility="onchange",
        help="Téléverser un fichier CV en Français.",
    )

    cv_en = fields.Many2one(
        string="CV EN",
        comodel_name="ir.attachment",
        domain="[('res_model', '=', 'res.partner'), ('res_id', '=', id)]",
        track_visibility="onchange",
        help="Téléverser un fichier CV en Anglais.",
    )

    portfolio_fr = fields.Many2one(
        string="Portfolio FR",
        comodel_name="ir.attachment",
        domain="[('res_model', '=', 'res.partner'), ('res_id', '=', id)]",
        track_visibility="onchange",
        help="Téléverser un fichier Portfolio en Français.",
    )

    portfolio_en = fields.Many2one(
        string="Portfolio EN",
        comodel_name="ir.attachment",
        domain="[('res_model', '=', 'res.partner'), ('res_id', '=', id)]",
        track_visibility="onchange",
        help="Téléverser un fichier Portfolio en Anglais.",
    )

    diplome_fr = fields.Many2one(
        string="Diplôme FR",
        comodel_name="ir.attachment",
        domain="[('res_model', '=', 'res.partner'), ('res_id', '=', id)]",
        track_visibility="onchange",
        help="Téléverser un fichier Diplôme en Français.",
    )

    diplome_en = fields.Many2one(
        string="Diplôme EN",
        comodel_name="ir.attachment",
        domain="[('res_model', '=', 'res.partner'), ('res_id', '=', id)]",
        track_visibility="onchange",
        help="Téléverser un fichier Diplôme en Anglais.",
    )

    evaluation_scolaire_fr = fields.Many2one(
        string="Évaluation scolaire FR",
        comodel_name="ir.attachment",
        domain="[('res_model', '=', 'res.partner'), ('res_id', '=', id)]",
        track_visibility="onchange",
        help="Téléverser un fichier Évaluation scolaire en Français.",
    )

    evaluation_scolaire_en = fields.Many2one(
        string="Évaluation scolaire EN",
        comodel_name="ir.attachment",
        domain="[('res_model', '=', 'res.partner'), ('res_id', '=', id)]",
        track_visibility="onchange",
        help="Téléverser un fichier Évaluation scolaire en Anglais.",
    )

    aspiration = fields.Html(
        string="Aspiration",
        track_visibility="onchange",
    )

    objectif_carriere = fields.Html(
        string="Objectif carrière",
        track_visibility="onchange",
    )

    emploi_precedent = fields.Html(
        string="Emploi précédent",
        help=(
            "Mettez vos réalisations, date début, date fin, responsabilités"
            " spécifiques."
        ),
    )

    competence = fields.Html(string="Compétence")

    experience = fields.Html(string="Expérience")

    avis_juridique = fields.Html(string="Avis juridique")

    # TODO employeur_responsable_principal m2o res.partner
    # TODO employeur_responsable_secondaire m2o res.partner
    # TODO employeur_responsable_autres m2m res.partner

    @api.depends(
        "member_lines",
        "member_lines.membership_id.is_feature_travailleur_libre",
        "member_lines.membership_id.is_feature_entreprise_bronze",
        "member_lines.membership_id.is_feature_entreprise_argent",
        "member_lines.membership_id.is_feature_entreprise_or",
        "membership_state",
    )
    def _compute_is_feature(self):
        for rec in self:
            if rec.member_lines:
                rec.is_feature_entreprise_bronze = False
                rec.is_feature_entreprise_argent = False
                rec.is_feature_entreprise_or = False
                rec.is_travailleur_libre = False
                rec.est_travailleur = False
                rec.est_employeur = False

                for member_line in rec.member_lines:
                    if member_line.membership_id.is_feature_travailleur_libre:
                        rec.is_feature_travailleur_libre = True
                        rec.est_travailleur = True

                    if member_line.membership_id.is_feature_entreprise_bronze:
                        rec.is_feature_entreprise_bronze = True
                        rec.est_employeur = True

                    if member_line.membership_id.is_feature_entreprise_argent:
                        rec.is_feature_entreprise_argent = True
                        rec.est_employeur = True

                    if member_line.membership_id.is_feature_entreprise_or:
                        rec.is_feature_entreprise_or = True
                        rec.est_employeur = True

    @api.model
    def default_stage_travailleur_id(self):
        stage_id = self.env["tdm.travailleur.stage"].search(
            [("is_init", "=", True)], limit=1
        )
        if not stage_id:
            # Take first one
            stage_id = self.env["tdm.travailleur.stage"].search([], limit=1)

        return stage_id
