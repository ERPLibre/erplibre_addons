# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import json

from odoo.tests import tagged

from .. import upgrade
from .common import StudioCase

MODULE = "studio_test_migration"
ITEM = "x_studio_test_item"


@tagged("post_install", "-at_install")
class TestMigration(StudioCase):
    """The upgrade of a project recorded in the form of 18.0.1.1.0: the
    columns of its single app, a rule without a group, the snapshot of
    what it applied."""

    def setUp(self):
        super().setUp()
        cr = self.env.cr
        cr.execute(
            "ALTER TABLE erplibre_studio_project ADD COLUMN IF NOT EXISTS app_name "
            "varchar, ADD COLUMN IF NOT EXISTS app_icon varchar, "
            "ADD COLUMN IF NOT EXISTS app_sequence integer"
        )

    def test_a_project_of_the_former_version(self):
        project = self.make_project(MODULE)
        line = self.make_model(project, "Studio test item", model=ITEM)
        rule = project._studio_save_rule(
            {
                "name": "Studio test rule",
                "model": ITEM,
                "domain": "[('create_uid', '=', user.id)]",
                "global_rule": True,
                "perm_read": True,
            }
        )
        project.action_apply()
        # The project as the former version left it: the app in columns of
        # the project, its model « in the app » without an app line, a rule
        # without group nor flag, the snapshot with a single « app ».
        snapshot = json.loads(project.applied_snapshot)
        snapshot["app"] = {"name": "Studio test old app", "icon": "", "sequence": 7}
        for key in ("apps", "groups"):
            snapshot.pop(key)
        for item in snapshot["models"]:
            item.pop("app")
        for item in snapshot["rules"]:
            for key in ("global_rule", "group_lines", "group_refs"):
                item.pop(key)
        cr = self.env.cr
        cr.execute(
            "UPDATE erplibre_studio_project SET app_name = %s, app_icon = NULL, "
            "app_sequence = 7, applied_snapshot = %s WHERE id = %s",
            ["Studio test old app", json.dumps(snapshot), project.id],
        )
        cr.execute(
            "UPDATE erplibre_studio_model SET app_id = NULL WHERE id = %s", [line.id]
        )
        cr.execute(
            "DELETE FROM erplibre_studio_app WHERE project_id = %s", [project.id]
        )
        cr.execute(
            "UPDATE erplibre_studio_rule SET global_rule = false, group_refs = NULL "
            "WHERE id = %s",
            [rule.id],
        )
        self.env.invalidate_all()
        # The former snapshot reads in the current form.
        loaded = project._studio_load_snapshot(project.applied_snapshot)
        self.assertEqual(loaded["apps"][0]["xml_name"], "menu_app")
        self.assertEqual(loaded["models"][0]["app"], "menu_app")
        self.assertTrue(loaded["rules"][0]["global_rule"])
        upgrade.migrate_projects(self.env)
        self.env.invalidate_all()
        app = project.app_ids
        self.assertEqual(
            (app.xml_name, app.name, app.menu_sequence),
            ("menu_app", "Studio test old app", 7),
        )
        self.assertEqual(line.app_id, app)
        self.assertTrue(rule.global_rule)
        self.assertEqual(rule.group_refs, "[]")
        self.assertEqual(project.applied_snapshot, project._current_snapshot())
        self.assertEqual(project.state, "applied")
        # A second run changes nothing.
        upgrade.migrate_projects(self.env)
        self.assertEqual(len(project.app_ids), 1)
        # The app is the one Apply made: its menu keeps its external id.
        project._studio_save_app({"id": app.id, "name": "Studio test old app"})
        project.action_apply()
        self.assertEqual(len(self.module_records(MODULE, "ir.ui.menu")), 2)
