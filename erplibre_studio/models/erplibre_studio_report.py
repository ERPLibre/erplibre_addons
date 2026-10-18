# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import hashlib
import json

from markupsafe import Markup, escape
from odoo import models
from odoo.exceptions import UserError
from odoo.tools import sql

from .. import arch as studio_arch
from .erplibre_studio_project import CREATED_FIELDS, MODULE_OWNING_STATES

# The sections of a removal report, in the order they show.
REPORT_SECTIONS = (
    "models",
    "fields",
    "tables",
    "groups",
    "categories",
    "menus",
    "actions",
    "views",
    "access",
    "rules",
    "members",
    "others",
)


def report_digest(report):
    """The digest of ``report``: what the user confirmed, compared again by
    the action it confirms."""
    return hashlib.sha256(
        json.dumps(report, sort_keys=True, default=str).encode()
    ).hexdigest()


def report_html(env, report):
    """The HTML of ``report`` (``_studio_removal_report``), every value
    escaped."""
    _ = env._
    titles = {
        "models": _("Models and their records"),
        "fields": _("Fields and their values"),
        "tables": _("Relation tables"),
        "groups": _("Groups and their members"),
        "categories": _("Categories of groups"),
        "menus": _("Menus"),
        "actions": _("Actions"),
        "views": _("Views"),
        "access": _("Access rights"),
        "rules": _("Record rules"),
        "members": _("Members who lose a group"),
        "others": _("Other records deleted with them"),
    }

    def text(section, item):
        if section == "models":
            return _(
                "%(name)s (%(model)s): %(count)s record(s)",
                name=item["name"],
                model=item["model"],
                count=item["count"],
            )
        if section == "fields":
            return _(
                "%(label)s (%(model)s.%(name)s): %(filled)s value(s)",
                label=item["label"],
                model=item["model"],
                name=item["name"],
                filled=item["filled"],
            )
        if section == "groups":
            return _(
                "%(name)s: %(users)s member(s)",
                name=item["name"],
                users=item["users"],
            )
        if section == "members":
            return _(
                "%(name)s: %(users)s member(s) of %(via)s lose it",
                name=item["name"],
                users=item["users"],
                via=item["via"],
            )
        if section == "access":
            return f"{item['name']} ({item['group']})"
        if section == "rules":
            return f"{item['name']} ({item['model']})"
        if section == "views":
            kind = _("default") if item["kind"] == "default" else _("inherited")
            return f"{item['name']} ({kind})"
        if section == "tables":
            return item
        return item["name"]

    parts = []
    for section in REPORT_SECTIONS:
        items = report.get(section) or []
        if not items:
            continue
        lines = Markup("").join(
            Markup("<li>%s</li>") % escape(text(section, item)) for item in items
        )
        parts.append(
            Markup('<h5 class="mt-2">%s (%s)</h5><ul class="mb-1">%s</ul>')
            % (titles[section], len(items), lines)
        )
    if report.get("changes_removed"):
        parts.append(
            Markup("<p>%s</p>")
            % _(
                "%(count)s change(s) of the default views go with these views.",
                count=report["changes_removed"],
            )
        )
    if not parts:
        return Markup("<p>%s</p>") % _("Nothing.")
    return Markup("").join(parts)


class ErplibreStudioProject(models.Model):
    """What Revert, and an Apply that removes, take out of the database:
    a report the user confirms, by its digest."""

    _inherit = "erplibre.studio.project"

    def _studio_count(self, table, column=None):
        """The rows of ``table``; with ``column``, those where it is set."""
        if not sql.table_exists(self.env.cr, table):
            return 0
        query = f'SELECT count(*) FROM "{table}"'
        if column:
            if not sql.column_exists(self.env.cr, table, column):
                return 0
            query += f' WHERE "{column}" IS NOT NULL'
        self.env.cr.execute(query)
        return self.env.cr.fetchone()[0]

    def _studio_leaving_fields(self, records):
        """The ir.model.fields that leave with ``records``: the custom fields
        among them, the fields of their models and those pointing at
        them."""
        Fields = self.env["ir.model.fields"].sudo()
        leaving = records.get("fields", Fields).filtered(lambda f: f.state == "manual")
        models_ = records.get("models", self.env["ir.model"])
        if models_:
            names = models_.mapped("model")
            leaving |= Fields.search(
                ["|", ("model", "in", names), ("relation", "in", names)]
            )
        return leaving

    def _studio_removal_report(self, records):
        """What removing ``records`` ({kind: records}, kinds of
        REMOVAL_ORDER, plus « views » and « fields ») takes out of the
        database: {models: [{model, name, count}], fields: [{model, name,
        label, filled}], views: [{name, kind}], changes_removed, menus,
        actions, access: [{name, group}], rules: [{name, model}], groups:
        [{name, users}], categories, tables}. A read, in sudo."""
        self.ensure_one()
        self.env.flush_all()
        records = {
            kind: value.sudo().with_context(active_test=False).exists()
            for kind, value in records.items()
            if value
        }
        empty = self.env["ir.model"].sudo()
        models_ = records.get("models", empty)
        removed_models = set(models_.mapped("model"))
        report = {
            "models": [],
            "fields": [],
            "views": [],
            "changes_removed": 0,
            "menus": [],
            "actions": [],
            "access": [],
            "rules": [],
            "groups": [],
            "categories": [],
            "tables": [],
            "members": [],
            "others": [],
        }
        for model in models_.sorted("model"):
            Model = self.env.get(model.model)
            table = Model._table if Model is not None else model.model.replace(".", "_")
            report["models"].append(
                {
                    "model": model.model,
                    "name": model.name,
                    "count": self._studio_count(table),
                }
            )
        for field in records.get("fields", self.env["ir.model.fields"]).sorted(
            lambda f: (f.model, f.name)
        ):
            if field.state != "manual" or field.model in removed_models:
                continue
            Model = self.env.get(field.model)
            if field.store and field.ttype not in studio_arch.X2MANY_TYPES:
                filled = (
                    self._studio_count(Model._table, field.name)
                    if Model is not None
                    else 0
                )
            elif field.ttype == "many2many":
                filled = self._studio_count(field.relation_table or "")
            else:
                filled = 0
            report["fields"].append(
                {
                    "model": field.model,
                    "name": field.name,
                    "label": field.field_description,
                    "filled": filled,
                }
            )
        for kind, label in (("primary_views", "default"), ("views", "inherited")):
            for view in records.get(kind, self.env["ir.ui.view"]).sorted("name"):
                report["views"].append({"name": view.name, "kind": label})
        primary = records.get("primary_views", self.env["ir.ui.view"])
        report["changes_removed"] = len(
            self.change_ids.filtered(lambda c: c.view_id in primary)
        )
        for kind in ("menus", "actions", "categories"):
            report[kind] = [
                {"name": record.display_name}
                for record in records.get(kind, empty).sorted("id")
            ]
        report["access"] = [
            {"name": row.name, "group": row.group_id.full_name or ""}
            for row in records.get("access", self.env["ir.model.access"]).sorted("name")
        ]
        report["rules"] = [
            {"name": rule.name, "model": rule.model_id.model}
            for rule in records.get("rules", self.env["ir.rule"]).sorted("name")
        ]
        report["groups"] = [
            {"name": group.full_name, "users": len(group.users)}
            for group in records.get("groups", self.env["res.groups"]).sorted("id")
        ]
        leaving = self._studio_leaving_fields(records)
        tables = {
            f.relation_table
            for f in leaving
            if f.state == "manual" and f.ttype == "many2many" and f.relation_table
        }
        if tables:
            kept = (
                self.env["ir.model.fields"]
                .sudo()
                .search([("relation_table", "in", list(tables))])
                - leaving
            )
            tables -= set(kept.mapped("relation_table"))
        report["tables"] = sorted(tables)
        # Made by hand, these refuse the removal (``_studio_check_cascade``);
        # the filters of the models go with them.
        report["others"] = sorted(
            (
                {"name": self._studio_record_label(record)}
                for rows in self._studio_cascade_records(models_, leaving)
                for record in rows
            ),
            key=lambda item: item["name"],
        )
        return report

    def _studio_created_records(self):
        """{kind: records} of everything the project created."""
        self.ensure_one()
        records = {kind: self[name] for kind, name in CREATED_FIELDS.items()}
        records["views"] = self.studio_view_ids
        records["fields"] = self.field_ids
        return records

    def _studio_revert_refusal(self, checks=True):
        """Why Revert is refused now, or False: while the generated module is
        installed, what the project applied is the module's (its external ids
        are under the module, its models are defined by it), and only its
        uninstall removes it; with ``checks``, the refusal of the checks of
        the removal (``_studio_check_removal``)."""
        self.ensure_one()
        self.invalidate_recordset(["module_id", "module_state"])
        owned = self.created_model_ids.exists().filtered(lambda m: m.state != "manual")
        if owned or self.module_state in MODULE_OWNING_STATES:
            return self.env._(
                "Uninstall the module %(module)s first: what the project applied "
                "belongs to it.",
                module=self.module_name,
            )
        if checks:
            try:
                self._studio_check_removal(self._studio_created_records())
            except UserError as exc:
                return exc.args[0]
        return False

    def _studio_revert_report(self):
        """{report, digest, refused}: what Revert removes now, its digest, and
        why Revert is refused (or False)."""
        self.ensure_one()
        report = self._studio_removal_report(self._studio_created_records())
        return {
            "report": report,
            "digest": report_digest(report),
            "refused": self._studio_revert_refusal(),
        }

    def _studio_kept_names(self):
        """{kind: names} of the external ids, under the module, of what Apply
        keeps, from the lines of the draft; for « fields », the (model,
        name) of the new fields."""
        self.ensure_one()
        kept = {kind: set() for kind in CREATED_FIELDS}
        kept["views"] = set()
        for line in self.new_model_ids:
            names = line._studio_xml_names()
            kept["models"].add(names["model"])
            kept["actions"].add(names["action"])
            kept["menus"].add(names["menu"])
            for view_type in studio_arch.MODEL_VIEW_TYPES:
                kept["primary_views"].add(names[view_type])
        for app in self.app_ids:
            if app._studio_menu_models():
                kept["menus"].add(app.xml_name)
            if app.group_line_ids:
                kept["categories"].add(app._studio_xml_names()["category"])
        kept["groups"] = set(self.group_line_ids.mapped("xml_name"))
        kept["access"] = set(self.access_line_ids.mapped("xml_name"))
        kept["rules"] = set(self.rule_line_ids.mapped("xml_name"))
        for view in self.change_ids.mapped("view_id"):
            kept["views"].add(self._studio_xmlname(view))
        kept["fields"] = {
            (model, name) for model, name, _d, _c in self._studio_all_definitions()
        }
        return kept

    def _studio_apply_removals(self):
        """{kind: records} of what the next Apply removes: what the project
        created that the draft no longer has."""
        self.ensure_one()
        created = self._studio_created_records()
        kept = self._studio_kept_names()
        Data = self.env["ir.model.data"].sudo()
        removals = {}
        for kind, records in created.items():
            records = records.exists()
            if kind == "fields":
                removals[kind] = records.filtered(
                    lambda f: (f.model, f.name) not in kept["fields"]
                )
                continue
            if not records:
                continue
            names = {
                data.res_id: data.name
                for data in Data.search(
                    [
                        ("module", "=", self.module_name),
                        ("model", "=", records._name),
                        ("res_id", "in", records.ids),
                    ]
                )
            }
            removals[kind] = records.filtered(
                lambda r, k=kind: names.get(r.id) not in kept[k]
            )
        return removals

    def _studio_apply_report(self):
        """{report, digest, confirm}: what the next Apply removes from the
        database; ``confirm`` when it holds records, values or group
        members, which Apply then asks to confirm by the digest."""
        self.ensure_one()
        report = self._studio_removal_report(self._studio_apply_removals())
        report["members"] = [
            {
                "name": dropped.full_name,
                "via": record.full_name,
                "users": len(users),
            }
            for record, dropped, users in self._studio_group_losses()
            if users
        ]
        confirm = (
            any(item["count"] for item in report["models"])
            or any(item["filled"] for item in report["fields"])
            or any(item["users"] for item in report["groups"])
            or any(item["users"] for item in report["members"])
        )
        return {"report": report, "digest": report_digest(report), "confirm": confirm}

    def _studio_check_digest(self, kind, digest):
        """Raise UserError unless ``digest`` is the one of the report of
        ``kind`` (« revert », « apply ») now: the user confirmed what the
        action removes. Server code in sudo, and an Apply that removes no
        data, are not asked."""
        self.ensure_one()
        if self.env.su:
            return
        if kind == "revert":
            expected = self._studio_revert_report()["digest"]
            message = self.env._(
                "What Revert removes changed since it was shown: review it again."
            )
        else:
            answer = self._studio_apply_report()
            if not answer["confirm"]:
                return
            expected = answer["digest"]
            message = self.env._(
                "Apply removes records, values or group members: review what it "
                "removes and confirm it."
            )
        if digest != expected:
            raise UserError(message)

    # ── project form ────────────────────────────────────────────────────

    def _studio_confirm_wizard(self, mode):
        self.ensure_one()
        self._check_studio_access()
        if mode == "revert":
            answer = self._studio_revert_report()
        else:
            answer = self._studio_apply_report()
        wizard = self.env["erplibre.studio.revert.wizard"].create(
            {
                "project_id": self.id,
                "mode": mode,
                "digest": answer["digest"],
                "refused": answer.get("refused") or False,
                "report_html": report_html(self.env, answer["report"]),
            }
        )
        titles = {
            "revert": self.env._("Revert %(name)s", name=self.name),
            "apply": self.env._("Apply %(name)s", name=self.name),
        }
        return {
            "type": "ir.actions.act_window",
            "name": titles[mode],
            "res_model": wizard._name,
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_revert_wizard(self):
        """The confirmation of Revert: what it removes, then Revert."""
        return self._studio_confirm_wizard("revert")

    def action_apply_wizard(self):
        """Apply; when it removes records, values or group members, its
        confirmation first."""
        self.ensure_one()
        self._check_studio_access()
        if not self._studio_apply_report()["confirm"]:
            return self.action_apply()
        return self._studio_confirm_wizard("apply")
