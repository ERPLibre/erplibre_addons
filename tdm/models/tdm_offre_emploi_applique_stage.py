from odoo import _, api, fields, models


class TdmOffreEmploiAppliqueStage(models.Model):
    _name = "tdm.offre.emploi.applique.stage"
    _inherit = "portal.mixin"
    _description = "tdm_offre_emploi_applique_stage"

    name = fields.Char()

    def _compute_access_url(self):
        super(TdmOffreEmploiAppliqueStage, self)._compute_access_url()
        for tdm_offre_emploi_applique_stage in self:
            tdm_offre_emploi_applique_stage.access_url = (
                "/my/tdm_offre_emploi_applique_stage/%s"
                % tdm_offre_emploi_applique_stage.id
            )
