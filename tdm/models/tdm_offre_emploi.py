from odoo import _, api, fields, models


class TdmOffreEmploi(models.Model):
    _name = "tdm.offre.emploi"
    _inherit = "portal.mixin"
    _description = "tdm_offre_emploi"

    name = fields.Char()

    def _compute_access_url(self):
        super(TdmOffreEmploi, self)._compute_access_url()
        for tdm_offre_emploi in self:
            tdm_offre_emploi.access_url = (
                "/my/tdm_offre_emploi/%s" % tdm_offre_emploi.id
            )
