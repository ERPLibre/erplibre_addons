from odoo import _, api, fields, models


class TdmOffreEmploiStage(models.Model):
    _name = "tdm.offre.emploi.stage"
    _inherit = "portal.mixin"
    _description = "tdm_offre_emploi_stage"

    name = fields.Char()

    def _compute_access_url(self):
        super(TdmOffreEmploiStage, self)._compute_access_url()
        for tdm_offre_emploi_stage in self:
            tdm_offre_emploi_stage.access_url = (
                "/my/tdm_offre_emploi_stage/%s" % tdm_offre_emploi_stage.id
            )
