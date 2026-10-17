# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from lxml import etree
from odoo.addons.erplibre_developer.tests.common import DeveloperMixin
from odoo.tests import new_test_user
from odoo.tests.common import TransactionCase

from ..models.erplibre_studio_project import PREVIEW_KEY

PIVOT_ARCH = """
<pivot string="Partners">
    <field name="country_id" type="row"/>
    <field name="partner_latitude" type="measure"/>
</pivot>
"""

TIMELINE_ARCH = """
<timeline date_start="create_date" date_stop="write_date" default_group_by="user_id">
    <field name="name"/>
    <templates>
        <t t-name="timeline-item">
            <div class="o_studio_test_item">
                <span t-esc="record.name"/>
            </div>
        </t>
    </templates>
</timeline>
"""


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

    def make_view(self, view_type, arch, model="res.partner", xml_id=None):
        """A primary view made for the test; ``xml_id`` (« module.name »)
        gives it an external id, which a generation needs."""
        view = self.env["ir.ui.view"].create(
            {
                "name": f"erplibre_studio test {view_type}",
                "model": model,
                "type": view_type,
                "arch": arch,
                "priority": 1000,
            }
        )
        if xml_id:
            module, name = xml_id.split(".")
            self.env["ir.model.data"].create(
                {
                    "module": module,
                    "name": name,
                    "model": "ir.ui.view",
                    "res_id": view.id,
                }
            )
        return view

    def timeline_available(self):
        return "timeline" in self.Project._view_types()

    def make_users(self):
        """(editor, other): two Settings administrators."""
        groups = "base.group_user,base.group_system"
        return (
            new_test_user(self.env, login="erplibre_studio_j2_editor", groups=groups),
            new_test_user(self.env, login="erplibre_studio_j2_other", groups=groups),
        )

    def preview_key(self, project):
        return {PREVIEW_KEY: f"{project.id}:{project.draft_revision}"}

    def view_arch(self, view, user=None, context=None, model="res.partner"):
        """The arch get_view gives ``user`` for ``view``, as an element."""
        Model = self.env[model]
        if user:
            Model = Model.with_user(user)
        Model = Model.with_context(**(context or {}))
        return etree.fromstring(Model.get_view(view.id, view.type)["arch"])

    def studio_views_of(self, module_name):
        data = self.env["ir.model.data"].search(
            [("module", "=", module_name), ("model", "=", "ir.ui.view")]
        )
        return self.env["ir.ui.view"].browse(data.mapped("res_id"))

    def check_apply_is_idempotent(self, project, view):
        """Apply twice: one inherited view on ``view``, unchanged by the
        second Apply. Return it."""
        project.action_apply()
        self.assertEqual(project.state, "applied")
        studio = project.studio_view_ids.filtered(lambda v: v.inherit_id == view)
        self.assertEqual(len(studio), 1)
        self.assertEqual(
            (studio.mode, studio.type, studio.model),
            ("extension", view.type, view.model),
        )
        arch = studio.arch
        project.action_apply()
        again = project.studio_view_ids.filtered(lambda v: v.inherit_id == view)
        self.assertEqual(again, studio)
        self.assertEqual(again.arch, arch)
        self.assertEqual(
            self.studio_views_of(project.module_name), project.studio_view_ids
        )
        return studio


class StudioCase(StudioMixin, TransactionCase):
    pass
