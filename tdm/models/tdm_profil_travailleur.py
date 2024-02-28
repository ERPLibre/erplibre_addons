from odoo import _, api, fields, models


class TdmProfilTravailleur(models.Model):
    _name = "tdm.profil.travailleur"
    _inherit = "portal.mixin"
    _description = "tdm_profil_travailleur"

    name = fields.Char()

    def _compute_access_url(self):
        super(TdmProfilTravailleur, self)._compute_access_url()
        for tdm_profil_travailleur in self:
            tdm_profil_travailleur.access_url = (
                "/my/tdm_profil_travailleur/%s" % tdm_profil_travailleur.id
            )
