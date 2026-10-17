# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import _, fields, models
from odoo.exceptions import UserError


class DevopsRequirement(models.Model):
    """Rattache un requis à son guide détaillé et aux cartes qui le citent.

    L'extension vit ici et non dans erplibre_devops_requirement : le guide
    dépend des requis, pas l'inverse, et un module de requis installé seul
    ne connaît pas `devops.guide`.
    """

    _inherit = "devops.requirement"

    guide_id = fields.Many2one(
        "devops.guide",
        string="Guide",
        ondelete="set null",
        index=True,
        help="Detailed guide page of this requirement.",
    )
    guide_card_ids = fields.One2many(
        "devops.guide.card", "requirement_id", string="Guide cards"
    )

    def action_open_guide(self):
        """Ouvre le guide détaillé du requis, comme le bouton Preview.

        Lève UserError sans guide : le bouton du formulaire est masqué dans
        ce cas, mais la méthode reste appelable par RPC.
        """
        self.ensure_one()
        if not self.guide_id:
            raise UserError(_("This requirement has no guide page."))
        return self.guide_id.action_preview()
