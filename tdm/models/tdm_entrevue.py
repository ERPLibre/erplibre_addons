from odoo import _, api, fields, models


class TdmEntrevue(models.Model):
    _name = "tdm.entrevue"
    _inherit = "portal.mixin"
    _description = "tdm_entrevue"

    name = fields.Char()

    def _compute_access_url(self):
        super(TdmEntrevue, self)._compute_access_url()
        for tdm_entrevue in self:
            tdm_entrevue.access_url = "/my/tdm_entrevue/%s" % tdm_entrevue.id
