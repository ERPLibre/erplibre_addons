# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from lxml import etree
from odoo.tests import new_test_user, tagged

from ..models.erplibre_studio_project import EXCLUDE_KEY, PREVIEW_KEY
from .common import StudioCase


@tagged("post_install", "-at_install")
class TestPreview(StudioCase):
    def setUp(self):
        super().setUp()
        self.editor = new_test_user(
            self.env,
            login="erplibre_studio_editor",
            groups="base.group_user,base.group_system",
        )
        self.other = new_test_user(
            self.env,
            login="erplibre_studio_other",
            groups="base.group_user,base.group_system",
        )
        self.project = self.make_project(user_id=self.editor.id)
        self.op(
            self.project,
            self.list,
            type="relabel",
            target="//field[@name='email']",
            value="Draft mail",
        )

    def label(self, user, context, view=None, view_type="list", name="email"):
        Partner = self.env["res.partner"].with_user(user).with_context(**context)
        arch = etree.fromstring(
            Partner.get_view((view or self.list).id, view_type)["arch"]
        )
        nodes = arch.xpath(f"//field[@name='{name}']")
        return nodes[0].get("string") if nodes else None

    def key(self, project=None):
        project = project or self.project
        return {PREVIEW_KEY: f"{project.id}:{project.draft_revision}"}

    def test_only_the_editor_sees_the_draft(self):
        # Each call fills the view cache: the other user and the context-free
        # call must not take the editor's entry, nor the reverse.
        self.assertEqual(self.label(self.editor, self.key()), "Draft mail")
        self.assertIsNone(self.label(self.other, self.key()))
        self.assertIsNone(self.label(self.editor, {}))
        self.assertIsNone(self.label(self.other, {}))
        self.assertEqual(self.label(self.editor, self.key()), "Draft mail")
        # A new revision is a new context value: the new draft shows.
        self.op(
            self.project,
            self.list,
            type="relabel",
            target="//field[@name='email']",
            value="Again",
        )
        self.assertEqual(self.label(self.editor, self.key()), "Again")
        # Another user becomes the editor: the draft follows the project.
        self.project.user_id = self.other
        self.assertEqual(self.label(self.other, self.key()), "Again")
        self.assertIsNone(self.label(self.editor, self.key()))

    def test_non_admin_never_sees_a_draft(self):
        user = new_test_user(
            self.env, login="erplibre_studio_user", groups="base.group_user"
        )
        self.project.user_id = user
        self.assertIsNone(self.label(user, self.key()))
        self.assertIsNone(self.label(user, {PREVIEW_KEY: "nonsense"}))

    def test_pending_field_placeholder(self):
        self.op(
            self.project,
            self.form,
            type="add_field",
            target="//field[@name='vat']",
            position="after",
            field={"ttype": "char", "field_description": "Nickname"},
        )
        self.op(
            self.project,
            self.list,
            type="add_field",
            target="//field[@name='email']",
            position="after",
            field={"ttype": "char", "field_description": "Nickname"},
        )
        Partner = (
            self.env["res.partner"].with_user(self.editor).with_context(**self.key())
        )
        form = etree.fromstring(Partner.get_view(self.form.id, "form")["arch"])
        placeholder = form.xpath("//div[hasclass('o_erplibre_studio_pending')]")
        self.assertEqual(len(placeholder), 1)
        self.assertEqual(placeholder[0].findtext("strong"), "Nickname")
        self.assertFalse(form.xpath("//field[@name='x_nickname']"))
        listing = etree.fromstring(Partner.get_view(self.list.id, "list")["arch"])
        self.assertFalse(listing.xpath("//field[@name='x_nickname']"))
        self.assertEqual(
            listing.xpath("//field[@name='email']")[0].get("string"),
            "Draft mail",
        )

    def test_draft_replaces_the_applied_view(self):
        """After Apply, the draft is computed without the applied view: a
        change never applies twice."""
        self.op(
            self.project,
            self.list,
            type="move",
            source="//field[@name='email']",
            target="//field[@name='complete_name']",
            position="before",
        )
        self.project.action_apply()
        self.assertEqual(self.label(self.other, {}), "Draft mail")
        self.op(
            self.project,
            self.list,
            type="hide",
            target="//field[@name='phone']",
            value=True,
        )
        arch = self.draft(self.project, self.list)
        self.assertEqual(self.columns(arch)[0], "email")
        self.assertEqual(len(arch.xpath("//field[@name='email']")), 1)
        Partner = (
            self.env["res.partner"].with_user(self.editor).with_context(**self.key())
        )
        preview = etree.fromstring(Partner.get_view(self.list.id, "list")["arch"])
        self.assertEqual(
            preview.xpath("//field[@name='phone']")[0].get("column_invisible"),
            "True",
        )
        self.assertEqual(self.columns(preview)[0], "email")

    def test_client_cannot_exclude_views(self):
        """The exclusion key sent by a client is ignored: neither its own
        answer nor the shared view cache lose an applied view."""
        self.project.action_apply()
        studio_view = self.project.studio_view_ids
        self.assertTrue(studio_view)
        user = new_test_user(
            self.env, login="erplibre_studio_plain", groups="base.group_user"
        )
        for login_user in (user, self.other):
            with self.subTest(user=login_user.login):
                forged = {EXCLUDE_KEY: [studio_view.id]}
                self.assertEqual(self.label(login_user, forged), "Draft mail")
                self.assertEqual(self.label(login_user, {}), "Draft mail")
        self.assertEqual(self.label(self.other, {}), "Draft mail")
        # The studio itself still leaves its views out of the base arch.
        base = self.project._base_arch(self.list)
        self.assertIsNone(base.xpath("//field[@name='email']")[0].get("string"))
