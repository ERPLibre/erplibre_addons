from odoo import _, api, fields, models


class TdmProfilEntrepriseStage(models.Model):
    _name = "tdm.profil.entreprise.stage"
    _inherit = "portal.mixin"
    _description = "tdm_profil_entreprise_stage"

    name = fields.Char()

    def _compute_access_url(self):
        super(TdmProfilEntrepriseStage, self)._compute_access_url()
        for tdm_profil_entreprise_stage in self:
            tdm_profil_entreprise_stage.access_url = (
                "/my/tdm_profil_entreprise_stage/%s"
                % tdm_profil_entreprise_stage.id
            )
