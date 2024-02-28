from odoo import _, api, fields, models


class TdmProfilEntreprise(models.Model):
    _name = "tdm.profil.entreprise"
    _inherit = "portal.mixin"
    _description = "tdm_profil_entreprise"

    name = fields.Char()

    def _compute_access_url(self):
        super(TdmProfilEntreprise, self)._compute_access_url()
        for tdm_profil_entreprise in self:
            tdm_profil_entreprise.access_url = (
                "/my/tdm_profil_entreprise/%s" % tdm_profil_entreprise.id
            )
