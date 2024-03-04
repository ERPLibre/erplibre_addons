from odoo import _, api, fields, models


class TdmSecteurActivite(models.Model):
    _name = "tdm.secteur_activite"
    _description = "tdm_secteur_activite"
    _order = "name, id"

    name = fields.Char()

    def _compute_access_url(self):
        super(TdmSecteurActivite, self)._compute_access_url()
        for tdm_secteur_activite in self:
            tdm_secteur_activite.access_url = (
                "/my/tdm_secteur_activite/%s" % tdm_secteur_activite.id
            )
