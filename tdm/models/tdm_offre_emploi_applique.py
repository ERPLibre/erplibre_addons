from odoo import _, api, fields, models


class TdmOffreEmploiApplique(models.Model):
    _name = "tdm.offre.emploi.applique"
    _inherit = "portal.mixin"
    _description = "tdm_offre_emploi_applique"

    name = fields.Char()

    def _compute_access_url(self):
        super(TdmOffreEmploiApplique, self)._compute_access_url()
        for tdm_offre_emploi_applique in self:
            tdm_offre_emploi_applique.access_url = (
                "/my/tdm_offre_emploi_applique/%s"
                % tdm_offre_emploi_applique.id
            )
