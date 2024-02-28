from odoo import _, api, fields, models


class TdmEntrevueStage(models.Model):
    _name = "tdm.entrevue.stage"
    _inherit = "portal.mixin"
    _description = "tdm_entrevue_stage"

    name = fields.Char()

    def _compute_access_url(self):
        super(TdmEntrevueStage, self)._compute_access_url()
        for tdm_entrevue_stage in self:
            tdm_entrevue_stage.access_url = (
                "/my/tdm_entrevue_stage/%s" % tdm_entrevue_stage.id
            )
