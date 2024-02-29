from odoo import _, api, fields, models


class TdmOffreEmploiStage(models.Model):
    _name = "tdm.offre.emploi.stage"
    _inherit = ["portal.mixin", "mail.activity.mixin", "mail.thread"]
    _description = "Stage sur offre d'emploi"
    _order = "sequence, name, id"

    name = fields.Char()

    description = fields.Char()

    is_init = fields.Boolean(
        help="Is init stage.",
    )

    sequence = fields.Integer(
        default=10,
        help="Used to order new project stages. Lower is better.",
    )

    fold = fields.Boolean(
        string="Folded in Pipeline",
        help=(
            "This stage is folded in the kanban view when there are no records"
            " in that stage to display."
        ),
    )

    def _compute_access_url(self):
        super(TdmOffreEmploiStage, self)._compute_access_url()
        for tdm_offre_emploi_stage in self:
            tdm_offre_emploi_stage.access_url = (
                "/my/tdm_offre_emploi_stage/%s" % tdm_offre_emploi_stage.id
            )
