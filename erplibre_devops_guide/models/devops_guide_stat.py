# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import api, fields, models


class DevopsGuideStat(models.Model):
    """Un chiffre du héros, littéral ou compté.

    Sans `count_model`, la valeur est `num` tel quel — un chiffre qui ne
    se déduit d'aucune table. Avec, elle est comptée ; et si
    `total_domain` est posé, elle s'affiche en rapport « n / total ».
    """

    _name = "devops.guide.stat"
    _inherit = "devops.guide.counter.mixin"
    _description = "Guide statistic"
    _order = "sequence, id"

    guide_id = fields.Many2one(
        "devops.guide",
        string="Guide",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10)
    num = fields.Char(string="Literal value", translate=True)
    label = fields.Char(string="Label", translate=True)
    action_xmlid = fields.Char(string="Action")
    total_domain = fields.Char(
        string="Total domain",
        help="When set, the value reads as a ratio: counted / total.",
    )
    value = fields.Char(string="Value", compute="_compute_value")

    @api.depends("num", "count_model", "count_domain", "total_domain")
    def _compute_value(self):
        for rec in self:
            if not rec.count_model:
                # Un Char vide se relit False : rendre une chaîne.
                rec.value = rec.num or ""
                continue
            count = rec._count_records(rec.count_model, rec.count_domain)
            if rec.total_domain:
                total = rec._count_records(rec.count_model, rec.total_domain)
                rec.value = f"{count} / {total}"
            else:
                rec.value = str(count)
