from odoo import _, api, fields, models


class TdmOffreEmploiApplique(models.Model):
    _name = "tdm.offre.emploi.applique"
    _inherit = ["portal.mixin", "mail.activity.mixin", "mail.thread"]
    _description = (
        "Application à une offre d'emploi. Offre emploi appliqué / Candidature"
        " reçus"
    )

    name = fields.Char(
        related="partner_travailleur_id.name",
        store=True,
        track_visibility="onchange",
    )

    active = fields.Boolean(
        string="Actif",
        track_visibility="onchange",
        default=True,
    )

    stage_id = fields.Many2one(
        comodel_name="tdm.offre.emploi.applique.stage",
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

    date_application = fields.Datetime(
        string="Date du dépôt",
        help="Date de l'application initialisation.",
        track_visibility="onchange",
    )

    offre_emploi_id = fields.Many2one(
        comodel_name="tdm.offre.emploi",
        string="Offre emploi",
        track_visibility="onchange",
    )

    def _compute_access_url(self):
        super(TdmOffreEmploiApplique, self)._compute_access_url()
        for tdm_offre_emploi_applique in self:
            tdm_offre_emploi_applique.access_url = (
                "/my/tdm_offre_emploi_applique/%s"
                % tdm_offre_emploi_applique.id
            )

    @api.model
    def default_stage_id(self):
        stage_id = self.env["tdm.offre.emploi.applique.stage"].search(
            [("is_init", "=", True)], limit=1
        )
        if not stage_id.exists():
            # Take first one
            stage_id = self.env["tdm.offre.emploi.applique.stage"].search(
                [], limit=1
            )
        return stage_id
