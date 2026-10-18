# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""The upgrade of the projects recorded by erplibre_studio 18.0.1.1.0: their
single app becomes an app line, their rules without a group on a model they
create become global, the snapshot of what they applied takes the current form. It runs from the
post-migration of 18.0.1.2.0, once the module is loaded and before the end
of the loading drops the columns of the removed fields, and does nothing a
second time."""

import logging

import psycopg2
from odoo.exceptions import ValidationError
from odoo.tools import sql

from .models.erplibre_studio_project import NO_TOUCH_KEY, RESTORE_KEY, SERVER_VALUES

_logger = logging.getLogger(__name__)

PROJECT_TABLE = "erplibre_studio_project"


def _server(env):
    return env(
        su=True,
        context=dict(env.context, **{NO_TOUCH_KEY: True, RESTORE_KEY: SERVER_VALUES}),
    )


def migrate_apps(env):
    """An app « menu_app » for each project that named one (the columns
    app_name, app_icon, app_sequence), with its models « in the app »."""
    cr = env.cr
    if not sql.column_exists(cr, PROJECT_TABLE, "app_name"):
        return
    cr.execute(
        f"SELECT id, app_name, app_icon, app_sequence FROM {PROJECT_TABLE} "
        "WHERE app_name IS NOT NULL AND trim(app_name) != ''"
    )
    env = _server(env)
    for project_id, name, icon, sequence in cr.fetchall():
        project = env["erplibre.studio.project"].browse(project_id)
        if project.app_ids.filtered(lambda a: a.xml_name == "menu_app"):
            continue
        vals = {
            "project_id": project_id,
            "xml_name": "menu_app",
            "name": name.strip(),
            "icon": icon or False,
            "menu_sequence": sequence or 50,
            "sequence": 10,
        }
        try:
            with cr.savepoint():
                app = env["erplibre.studio.app"].create(vals)
        except (ValidationError, psycopg2.Error):
            # An icon of a module no longer installed: the studio icon.
            _logger.warning("Studio project %s: app icon %s dropped", project_id, icon)
            app = env["erplibre.studio.app"].create(dict(vals, icon=False))
        project.new_model_ids.filtered(
            lambda m: m.menu_mode == "app" and not m.app_id
        ).write({"app_id": app.id})


def migrate_rules(env):
    """A rule without a group on a model its project creates is global, as
    it applied; on an existing model it stays without a group, which Apply
    refuses until it gets one (a global rule there would restrict every
    user). Every rule records the external ids of its groups."""
    env = _server(env)
    for rule in env["erplibre.studio.rule"].search([]):
        vals = {}
        if not (
            rule.group_ids or rule.group_line_ids or rule.global_rule
        ) and rule.model in (rule.project_id._studio_new_models()):
            vals["global_rule"] = True
        if not rule.group_refs:
            vals["group_refs"] = rule._studio_group_refs()
        if vals:
            rule.write(vals)


def migrate_snapshots(env):
    """The projects applied (or generated) record what they applied in the
    current form of the snapshot; their state stays."""
    cr = env.cr
    cr.execute(
        f"SELECT id FROM {PROJECT_TABLE} WHERE state != 'draft' "
        "AND applied_snapshot IS NOT NULL"
    )
    ids = [row[0] for row in cr.fetchall()]
    for project in env["erplibre.studio.project"].browse(ids):
        project._internal().write({"applied_snapshot": project._current_snapshot()})


def migrate_projects(env):
    migrate_apps(env)
    migrate_rules(env)
    migrate_snapshots(env)
