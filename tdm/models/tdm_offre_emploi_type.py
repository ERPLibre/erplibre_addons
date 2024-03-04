from odoo import _, api, fields, models


class TdmOffreEmploiType(models.Model):
    _name = "tdm.offre.emploi.type"
    _description = "tdm_offre_emploi_type"
    _order = "name, id"

    name = fields.Char()

    def _compute_access_url(self):
        super(TdmOffreEmploiType, self)._compute_access_url()
        for tdm_offre_emploi_type in self:
            tdm_offre_emploi_type.access_url = (
                "/my/tdm_offre_emploi_type/%s" % tdm_offre_emploi_type.id
            )
