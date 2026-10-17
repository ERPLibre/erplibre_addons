# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, models

from .erplibre_studio_project import EXCLUDE_KEY, ViewExclusion


class IrUiView(models.Model):
    _inherit = "ir.ui.view"

    @api.model
    def _get_inheriting_views_domain(self):
        """Leave out of a combined arch the views listed by the context: the
        studio views of a project, whose draft replaces them. Only a
        ``ViewExclusion`` counts, which the studio builds on the server."""
        domain = super()._get_inheriting_views_domain()
        excluded = self.env.context.get(EXCLUDE_KEY)
        if isinstance(excluded, ViewExclusion) and excluded:
            domain = [*domain, ("id", "not in", list(excluded))]
        return domain
