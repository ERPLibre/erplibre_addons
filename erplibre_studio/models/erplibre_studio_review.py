# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import json

from odoo import api, models
from odoo.exceptions import UserError

from .. import arch as studio_arch
from .erplibre_studio_project import PERMS

# The categories of the items of a review, in the order of its filters: the
# new fields, the other changes of views, the models, the security (access
# rows, rules, apps and groups).
REVIEW_CATEGORIES = ("fields", "views", "models", "security")
# The change types that define a new field: the category « fields ».
FIELD_CHANGE_TYPES = ("add_field",)


class ErplibreStudioEditor(models.AbstractModel):
    """The review of a project before Apply: every item of its draft, by
    view and by model, with what stops it from applying, and what Apply
    removes from the database."""

    _inherit = "erplibre.studio.editor"

    @api.model
    def get_review(self, project_id):
        """{revision, state, groups, removal, blocked} of the project
        ``project_id``. ``groups``: [{key, kind, title, ref, items}], each
        view the project adds, then the changes of each view (« view », a
        view added first), then each model of the project with its access
        rows and rules (« model »), the access rows and rules of the other
        models (« security »), the apps and groups (« apps »).
        Each item: {key, type, id, category (REVIEW_CATEGORIES), text,
        error, applied, target}; ``applied`` when the last Apply wrote it
        as it is, ``error`` why it does not apply (or False), ``target``
        where the editor shows it ({space, ...}). ``removal``: the answer
        of ``get_apply_report``. ``blocked``: why Apply refuses the draft
        now, or False. A read."""
        self._check_studio_access()
        project = self._read_project(project_id)
        review = _Review(self, project)
        review.add_changes()
        review.add_models()
        review.add_access()
        review.add_rules()
        review.add_apps()
        try:
            project._studio_check_apply()
            blocked = False
        except UserError as exc:
            blocked = exc.args[0]
        return {
            "revision": project.draft_revision,
            "state": project.state,
            "groups": review.result(),
            "removal": project._studio_apply_report(),
            "blocked": blocked,
        }


class _Review:
    """The groups of a review of ``project``, built item by item."""

    def __init__(self, editor, project):
        self.editor = editor
        self.project = project
        self.env = editor.env
        self.groups = {}
        self.labels = editor._view_type_labels()
        self.lines = {line.model: line for line in project.new_model_ids}
        # The views Apply created for the view lines, by id: their changes
        # sit in the group of their line.
        self.added = {
            line.view_id.id: line for line in project.view_line_ids if line.view_id
        }
        self.applied = self._applied_snapshot()

    # ── helpers ─────────────────────────────────────────────────────────

    def _applied_snapshot(self):
        """{kind: set of JSON}: the items of the last Apply, each as its
        ``_snapshot`` gives it; an item of the draft whose JSON is in its
        set is unchanged since then."""
        if not self.project.applied_snapshot:
            return {}
        snapshot = self.project._studio_load_snapshot(self.project.applied_snapshot)
        return {
            kind: {json.dumps(item, sort_keys=True) for item in items}
            for kind, items in snapshot.items()
        }

    def is_applied(self, kind, record):
        """Whether the last Apply wrote ``record`` (of the snapshot kind
        ``kind``) as the draft holds it."""
        item = record._snapshot()[0]
        return json.dumps(item, sort_keys=True) in self.applied.get(kind, ())

    def error_of(self, check, *args):
        """The message of the UserError ``check(*args)`` raises, or False."""
        try:
            check(*args)
        except UserError as exc:
            return exc.args[0]
        return False

    def model_name(self, model):
        line = self.lines.get(model)
        if line and model not in self.env:
            return line.name
        record = self.env["ir.model"].sudo()._get(model)
        return record.name or (line.name if line else model)

    def group(self, key, kind, title, ref):
        if key not in self.groups:
            self.groups[key] = {
                "key": key,
                "kind": kind,
                "title": title,
                "ref": ref or False,
                "items": [],
            }
        return self.groups[key]

    def model_group(self, model):
        """The group of ``model``: the one of its model line when the
        project creates it, else the one of its security."""
        _ = self.env._
        line = self.lines.get(model)
        if line:
            title = _("Model of the project") if line.applied else _("New model")
            return self.group(f"model:{model}", "model", title, model)
        title = _("Security of %(model)s", model=self.model_name(model))
        return self.group(f"security:{model}", "security", title, model)

    def add(self, group, kind, record, category, text, error, target, applied):
        group["items"].append(
            {
                "key": f"{kind}:{record.id}",
                "type": kind,
                "id": record.id,
                "category": category,
                "text": text,
                "error": error or False,
                "applied": applied,
                "target": target,
            }
        )

    # ── items ───────────────────────────────────────────────────────────

    def added_group(self, line):
        """The group of the view the view line ``line`` adds."""
        _ = self.env._
        label = self.labels.get(line.view_type, line.view_type)
        title = _("%(model)s — %(view)s", model=self.model_name(line.model), view=label)
        ref = f"{self.project.module_name}.{line._studio_xml_name()}"
        return self.group(f"added:{line.id}", "view", title, ref)

    def view_group(self, change):
        """The group of the view of ``change``: its view, the pending
        default view of its model line, or the view a view line adds."""
        _ = self.env._
        label = self.labels.get(change.view_type, change.view_type)
        added = change.view_line_id or self.added.get(change.view_id.id)
        if added:
            return self.added_group(added)
        line = change.model_line_id
        if line:
            ref = f"{self.project.module_name}.{line._studio_xml_names()[change.view_type]}"
            title = _("%(model)s — %(view)s", model=line.name or line.model, view=label)
            return self.group(
                f"pending:{line.id}:{change.view_type}", "view", title, ref
            )
        view = change.view_id.sudo()
        title = _(
            "%(model)s — %(view)s", model=self.model_name(change.model), view=label
        )
        return self.group(f"view:{view.id}", "view", title, view.xml_id or view.name)

    def add_changes(self):
        """The changes of views, view by view in the order of their first
        change; a change carries the path of its block in the draft and the
        error that keeps it out of the draft."""
        project = self.project
        self.add_views()
        changes = project.change_ids.sorted(lambda c: (c.sequence, c.id))
        done = set()
        for change in changes:
            key = (
                change.view_id.id,
                change.model_line_id.id,
                change.view_line_id.id,
                change.view_type,
            )
            if key in done:
                continue
            done.add(key)
            view = project._change_view(change)
            try:
                arch, errors = project._draft_arch(view, track=True)
                paths = studio_arch.change_paths(arch)
                failure = False
            except (UserError, studio_arch.ArchError) as exc:
                paths, errors = {}, {}
                failure = exc.args[0] if exc.args else str(exc)
            for item in project._view_changes(view):
                group = self.view_group(item)
                error = (
                    failure
                    or errors.get(item.id)
                    or self.error_of(project._studio_check_apply_change, item)
                )
                self.add(
                    group,
                    "change",
                    item,
                    "fields" if item.change_type in FIELD_CHANGE_TYPES else "views",
                    item.summary,
                    error,
                    {
                        "space": "view",
                        "model": item.model,
                        "view_id": item.view_id.id or False,
                        "view_type": item.view_type,
                        "path": (not error and paths.get(str(item.id))) or False,
                    },
                    self.is_applied("changes", item),
                )

    def add_views(self):
        """The views the project adds, each first in the group of its
        changes."""
        _ = self.env._
        project = self.project
        for line in project.view_line_ids:
            self.add(
                self.added_group(line),
                "view",
                line,
                "views",
                _(
                    "Create the default %(view)s view of %(model)s",
                    view=self.labels.get(line.view_type, line.view_type),
                    model=self.model_name(line.model),
                ),
                self.error_of(project._studio_check_apply_view, line),
                {
                    "space": "view",
                    "model": line.model,
                    "view_id": line.view_id.id or False,
                    "view_type": line.view_type,
                    "path": False,
                },
                self.is_applied("views", line),
            )

    def add_models(self):
        _ = self.env._
        project = self.project
        mail = project._studio_mail_available()
        for line in project.new_model_ids:
            if line.applied:
                text = _("Update the model %(name)s", name=line.name)
            else:
                text = _(
                    "Create the model %(name)s, its menu and its views", name=line.name
                )
            self.add(
                self.model_group(line.model),
                "model",
                line,
                "models",
                text,
                self.error_of(project._studio_check_apply_model, line, mail),
                {"space": "models", "model": line.model},
                self.is_applied("models", line),
            )

    def add_access(self):
        _ = self.env._
        project = self.project
        labels = {
            "perm_read": _("read"),
            "perm_write": _("write"),
            "perm_create": _("create"),
            "perm_unlink": _("delete"),
        }
        for line in project.access_line_ids:
            if line.group_line_id:
                group = f"{line.group_line_id.app_id.name} / {line.group_line_id.name}"
            elif line.group_id:
                group = line.group_id.sudo().full_name
            else:
                group = _("Every user")
            rights = [labels[perm] for perm in PERMS if line[perm]]
            text = _(
                "Rights of %(group)s on %(model)s: %(rights)s",
                group=group,
                model=self.model_name(line.model),
                rights=", ".join(rights) or _("none"),
            )
            self.add(
                self.model_group(line.model),
                "access",
                line,
                "security",
                text,
                self.error_of(project._studio_check_apply_access, line),
                {"space": "security", "tab": "access", "model": line.model},
                self.is_applied("access", line),
            )

    def add_rules(self):
        _ = self.env._
        project = self.project
        for rule in project.rule_line_ids:
            self.add(
                self.model_group(rule.model),
                "rule",
                rule,
                "security",
                _(
                    "Rule « %(name)s » on %(model)s",
                    name=rule.name,
                    model=self.model_name(rule.model),
                ),
                self.error_of(project._studio_check_apply_rule, rule),
                {"space": "security", "tab": "rules", "model": rule.model},
                self.is_applied("rules", rule),
            )

    def add_apps(self):
        _ = self.env._
        project = self.project
        target = {"space": "security", "tab": "apps"}
        title = _("Apps and groups")
        for app in project.app_ids:
            self.add(
                self.group("apps", "apps", title, False),
                "app",
                app,
                "security",
                _("App %(name)s", name=app.name),
                self.error_of(app._check_studio_app),
                target,
                self.is_applied("apps", app),
            )
        for group in project.group_line_ids:
            self.add(
                self.group("apps", "apps", title, False),
                "group",
                group,
                "security",
                _(
                    "Group %(name)s of the app %(app)s",
                    name=group.name,
                    app=group.app_id.name,
                ),
                self.error_of(project._studio_check_apply_group, group),
                target,
                self.is_applied("groups", group),
            )

    def result(self):
        """The groups that hold items, in the order they were made."""
        return [group for group in self.groups.values() if group["items"]]
