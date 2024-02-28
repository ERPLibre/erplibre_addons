from odoo import _, api, fields, models


class TdmProfilTravailleurStage(models.Model):
    _name = "tdm.profil.travailleur.stage"
    _inherit = "portal.mixin"
    _description = "tdm_profil_travailleur_stage"

    name = fields.Char()

    def _compute_access_url(self):
        super(TdmProfilTravailleurStage, self)._compute_access_url()
        for tdm_profil_travailleur_stage in self:
            tdm_profil_travailleur_stage.access_url = (
                "/my/tdm_profil_travailleur_stage/%s"
                % tdm_profil_travailleur_stage.id
            )
