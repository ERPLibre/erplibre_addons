# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.addons.erplibre_developer.tests.common import DeveloperMixin
from odoo.tests.common import TransactionCase


class StudioMixin(DeveloperMixin):
    """A studio project on the contact views, and its draft."""

    def setUp(self):
        super().setUp()
        # Apply adds custom fields to the registry: back to the database
        # state once the test is rolled back.
        self.addCleanup(self.registry.reset_changes)
        self.Project = self.env["erplibre.studio.project"]
        self.Editor = self.env["erplibre.studio.editor"]
        self.form = self.env.ref("base.view_partner_form")
        self.list = self.env.ref("base.view_partner_tree")

    def make_project(self, module_name="studio_test_partner", **vals):
        return self.Project.create(
            {"name": "Studio test", "module_name": module_name, **vals}
        )

    def op(self, project, view, **operation):
        return project._apply_operation(view, operation)

    def draft(self, project, view):
        arch, errors = project._draft_arch(view)
        self.assertFalse(errors)
        return arch

    def columns(self, arch):
        return [node.get("name") for node in arch.xpath("/list/field")]


class StudioCase(StudioMixin, TransactionCase):
    pass
