from odoo import _, api, fields, models


class TdmOffreEmploiAppliqueStage(models.Model):
    _name = "tdm.offre.emploi.applique.stage"
    _inherit = "portal.mixin"
    _description = "Stage sur application à une offre d'emploi"
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
        super(TdmOffreEmploiAppliqueStage, self)._compute_access_url()
        for tdm_offre_emploi_applique_stage in self:
            tdm_offre_emploi_applique_stage.access_url = (
                "/my/tdm_offre_emploi_applique_stage/%s"
                % tdm_offre_emploi_applique_stage.id
            )
