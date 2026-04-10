# © 2025 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo.addons.base.tests.common import BaseCommon


class ProjetDevCodeCommon(BaseCommon):
    """Shared fixtures for projet_dev_code tests."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env["project.project"].create(
            {"name": "Test Claude Project"}
        )

    def _make_task(self, **vals):
        """Create a project.task with sensible defaults."""
        defaults = {
            "name": "Dev Task",
            "project_id": self.project.id,
        }
        defaults.update(vals)
        return self.env["project.task"].create(defaults)
