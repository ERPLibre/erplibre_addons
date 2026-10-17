# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, models


class ErplibreStudioEditor(models.AbstractModel):
    _inherit = "erplibre.studio.editor"

    @api.model
    def _project_payload(self, project):
        """The version of the next generation, shown by the editor next to
        the state of the project."""
        data = super()._project_payload(project)
        data["version"] = project.version
        return data
