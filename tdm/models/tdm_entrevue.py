import uuid

from odoo import _, api, fields, models


class TdmEntrevue(models.Model):
    _name = "tdm.entrevue"
    _inherit = ["portal.mixin", "mail.activity.mixin", "mail.thread"]
    _description = "Entrevue entre un travailleur et une entreprise"

    name = fields.Char(
        store=True, compute="_compute_name", track_visibility="onchange"
    )

    active = fields.Boolean(
        string="Actif",
        track_visibility="onchange",
        default=True,
    )

    stage_id = fields.Many2one(
        comodel_name="tdm.entrevue.stage",
        string="Stage",
        default=lambda s: s.default_stage_id(),
        track_visibility="onchange",
    )

    partner_travailleur_id = fields.Many2one(
        comodel_name="res.partner",
        string="Travailleur",
        track_visibility="onchange",
        domain=[("est_travailleur", "=", True)],
    )

    partner_employeur_id = fields.Many2one(
        comodel_name="res.partner",
        string="Employeur",
        track_visibility="onchange",
        domain=[("est_employeur", "=", True)],
    )

    offre_emploi_id = fields.Many2one(
        comodel_name="tdm.offre.emploi",
        string="Offre emploi",
        related="offre_emploi_applique_id.offre_emploi_id",
        store=True,
        track_visibility="onchange",
    )

    offre_emploi_applique_id = fields.Many2one(
        comodel_name="tdm.offre.emploi.applique",
        string="Offre emploi appliqué",
        track_visibility="onchange",
    )

    evaluation_id = fields.Many2one(
        comodel_name="survey.survey",
        string="Évaluation",
        related="offre_emploi_id.evaluation_id",
        store=True,
        track_visibility="onchange",
    )

    date_debut_entrevue = fields.Datetime(
        string="Début entrevue",
        track_visibility="onchange",
    )

    show_jitsi_link = fields.Boolean(
        store=True, compute="_compute_show_jitsi_link"
    )

    url_jitsi_employeur = fields.Char(
        string="URL Jitsi travailleur",
        store=True,
        compute="_compute_name",
        track_visibility="onchange",
    )

    url_jitsi_travailleur = fields.Char(
        string="URL Jitsi employeur",
        store=True,
        compute="_compute_name",
        track_visibility="onchange",
    )

    # TODO dure_estime = fields.Float(string="Dure estimé")
    # TODO partner_employeur_responsable_principal_id = m2o res.partner
    # TODO partner_employeur_responsable_secondaire_id = m2o res.partner
    # TODO partner_employeur_responsable_autres_id = m2m res.partner

    @api.depends(
        "partner_travailleur_id",
        "partner_employeur_id",
        "partner_travailleur_id.name",
        "partner_employeur_id.name",
        "partner_travailleur_id.email",
        "partner_employeur_id.email",
        "offre_emploi_id",
    )
    def _compute_name(self):
        for rec in self:
            channel = f"{uuid.uuid4().hex}TdM{uuid.uuid4().hex}"
            url_jitsi = f"https://meet.jit.si/{channel}"
            name = ""
            if rec.partner_travailleur_id:
                name_travailleur = rec.partner_travailleur_id.name.replace(
                    " ", "%20"
                )
                name += f"{rec.partner_travailleur_id.name} - "
                email_travailleur = rec.partner_travailleur_id.email
                rec.url_jitsi_travailleur = (
                    f'{url_jitsi}#userInfo.displayName="{name_travailleur}"'
                )
                if email_travailleur:
                    rec.url_jitsi_travailleur += (
                        f'&userInfo.email="{email_travailleur}"'
                    )
            if rec.partner_employeur_id:
                name_employeur = rec.partner_employeur_id.name.replace(
                    " ", "%20"
                )
                name += f"{rec.partner_employeur_id.name} - "
                email_employeur = rec.partner_employeur_id.email

                rec.url_jitsi_employeur = (
                    f'{url_jitsi}#userInfo.displayName="{name_employeur}"'
                )
                if email_employeur:
                    rec.url_jitsi_employeur += (
                        f'&userInfo.email="{email_employeur}"'
                    )
            rec.name = name if name else "TODO"

    @api.depends(
        "partner_employeur_id",
        "partner_employeur_id.is_feature_entreprise_argent",
        "partner_employeur_id.is_feature_entreprise_or",
    )
    def _compute_show_jitsi_link(self):
        for rec in self:
            rec.show_jitsi_link = (
                rec.partner_employeur_id.is_feature_entreprise_argent
                or rec.partner_employeur_id.is_feature_entreprise_or
            )

    def _compute_access_url(self):
        super(TdmEntrevue, self)._compute_access_url()
        for tdm_entrevue in self:
            tdm_entrevue.access_url = "/my/tdm_entrevue/%s" % tdm_entrevue.id

    @api.model
    def default_stage_id(self):
        stage_id = self.env["tdm.entrevue.stage"].search(
            [("is_init", "=", True)], limit=1
        )
        if not stage_id.exists():
            # Take first one
            stage_id = self.env["tdm.entrevue.stage"].search([], limit=1)
        return stage_id
