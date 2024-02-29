from odoo import _, api, fields, models


class TdmTravailleurStage(models.Model):
    _name = "tdm.travailleur.stage"
    _description = "tdm_travailleur_stage"
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
