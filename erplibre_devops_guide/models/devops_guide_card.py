# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import api, fields, models


class DevopsGuideCard(models.Model):
    """Une carte : un problème, sa réponse, et au plus un bouton.

    Le bouton se résout dans cet ordre — `url` ouvre un onglet,
    `action_xmlid` appelle l'action, `count_model` ouvre ce modèle filtré
    par `count_domain`. Les trois vides : aucun bouton, ce qui rend une
    étape de feuille de route.

    `action_label` accepte le marqueur `{count}`, remplacé par le décompte
    quand `count_model` est posé. Un libellé reste ainsi juste quand les
    données bougent, là où un nombre écrit en dur dérive.
    """

    _name = "devops.guide.card"
    _inherit = "devops.guide.counter.mixin"
    _description = "Guide card"
    _order = "sequence, id"

    section_id = fields.Many2one(
        "devops.guide.section",
        string="Section",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10)
    # Numéro de l'étape, pour une section en feuille de route.
    num = fields.Char(string="Number")
    icon = fields.Char(
        string="Icon",
        help="Font Awesome class without the fa prefix, e.g. fa-database.",
    )
    title = fields.Char(string="Title", translate=True)
    problem = fields.Text(string="Problem", translate=True)
    solution = fields.Text(string="Solution", translate=True)
    action_xmlid = fields.Char(
        string="Action",
        help="XML id of an action, e.g. crm.crm_lead_action_pipeline.",
    )
    url = fields.Char(
        string="URL",
        help="Opened in a new tab, and takes precedence over the action.",
    )
    action_label = fields.Char(
        string="Button label",
        translate=True,
        help=(
            "The marker {count} is replaced by the counted figure when a "
            "counted model is set, so the label stays true as data changes. "
            "Without a counted model the marker is left as written."
        ),
    )
    resolved_label = fields.Char(
        string="Resolved label", compute="_compute_resolved_label"
    )

    @api.depends("action_label", "count_model", "count_domain")
    def _compute_resolved_label(self):
        for rec in self:
            label = rec.action_label or ""
            if rec.count_model and "{count}" in label:
                count = rec._count_records(rec.count_model, rec.count_domain)
                label = label.replace("{count}", str(count))
            rec.resolved_label = label
