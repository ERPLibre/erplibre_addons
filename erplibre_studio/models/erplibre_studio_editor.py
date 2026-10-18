# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models
from odoo.exceptions import UserError

from .. import arch as studio_arch
from .erplibre_studio_project import (
    NEW_FIELD_TYPES,
    PENDING_VIEW_OPERATIONS,
    PERMS,
    PREVIEW_KEY,
    protected_model,
)
from .studio_pending import is_pending_view, pending_view

FIELD_ATTRIBUTES = [
    "string",
    "type",
    "required",
    "readonly",
    "relation",
    "selection",
    "help",
    "store",
    "groupable",
    "searchable",
    "sortable",
    "aggregator",
]

PROJECT_ACTIONS = (
    "action_apply",
    "action_discard",
    "action_revert",
    "action_undo",
    "action_approve",
    "action_unapprove",
)
# The actions that remove from the database what the user confirmed.
DIGEST_ACTIONS = ("action_apply", "action_revert")
# The modes of the preview of a model not created yet.
PREVIEW_MODES = ("simulation", "real")


class ErplibreStudioEditor(models.AbstractModel):
    """The server side of the studio editor. Every call needs the Settings
    group and the developer mode; each operation answers with the new
    editor payload, computed from the draft of the project."""

    _name = "erplibre.studio.editor"
    _description = "ERPLibre studio editor"

    @api.model
    def _check_studio_access(self):
        self.env["erplibre.developer"]._check_panel_access()

    @api.model
    def _resolve_view(self, model, view_id, view_type, project=None):
        """The primary view the editor inherits: ``view_id``, or the default
        view of ``model`` for ``view_type``; for a model of ``project`` not
        created yet, its pending default view (``StudioPendingView``)."""
        Project = self.env["erplibre.studio.project"]
        if view_type not in Project._view_types():
            raise UserError(
                self.env._("The studio does not edit %(type)s views.", type=view_type)
            )
        if model not in self.env:
            line = project._studio_pending_line(model) if project else None
            if not line:
                raise UserError(self.env._("Unknown model %(model)s.", model=model))
            if view_type not in studio_arch.MODEL_VIEW_TYPES:
                raise UserError(
                    self.env._(
                        "Apply the model first: %(type)s needs its records.",
                        type=view_type,
                    )
                )
            return pending_view(line, view_type)
        View = self.env["ir.ui.view"].sudo()
        view = View.browse(int(view_id)).exists() if view_id else View
        if not view:
            view = View.browse(View.default_view(model, view_type))
        if not view:
            raise UserError(
                self.env._(
                    "%(model)s has no %(type)s view to inherit.",
                    model=model,
                    type=view_type,
                )
            )
        if view.model != model or view.type != view_type or view.mode != "primary":
            raise UserError(
                self.env._(
                    "The studio inherits a primary %(type)s view.",
                    type=view_type,
                )
            )
        return view

    @api.model
    def _read_project(self, project_id):
        """The project ``project_id`` as a read sees it: not opened, its
        editor and its revision unchanged."""
        Project = self.env["erplibre.studio.project"]
        project = Project.browse(int(project_id or 0)).exists()
        if not project:
            raise UserError(self.env._("Choose or create a studio project first."))
        return project

    @api.model
    def _project(self, project_id, pick_project=True, model=None):
        """The project ``project_id``; without one, unless ``pick_project``
        is False, the project that creates ``model``, else the last project
        of the user. Opening a project makes the user its editor, the one
        who sees its draft."""
        Project = self.env["erplibre.studio.project"]
        project = Project.browse(int(project_id)).exists() if project_id else Project
        if not project and pick_project and model:
            project = (
                self.env["erplibre.studio.model"]
                .search([("model", "=", model)], limit=1)
                .project_id
            )
        if not project and pick_project:
            project = Project.search([("user_id", "=", self.env.uid)], limit=1)
        if project and project.user_id != self.env.user:
            project.user_id = self.env.user
        return project

    @api.model
    def action_customize(
        self,
        model,
        view_id=False,
        view_type="form",
        action_id=False,
        project_id=False,
    ):
        """The client action of the editor on a view; on the default view of
        a model of the project ``project_id`` not created yet."""
        self._check_studio_access()
        Project = self.env["erplibre.studio.project"]
        project = Project.browse(int(project_id or 0)).exists()
        view = self._resolve_view(model, view_id, view_type, project)
        return {
            "type": "ir.actions.client",
            "tag": "erplibre_studio.editor",
            "name": self.env._("Studio"),
            "target": "current",
            "params": {
                "res_model": model,
                "view_id": view.id,
                "view_type": view.type,
                "action_id": action_id or False,
                "project_id": project_id or False,
            },
        }

    @api.model
    def _fields_payload(self, model, project):
        """The fields of ``model`` (simulated for a model of the project not
        created yet) with the new fields of the project on it, flagged
        ``project``, ``pending`` until Apply creates them, and their
        ``definition``."""
        line = project._studio_pending_line(model) if project else None
        if line:
            info = project._studio_simulated_fields(line)
            names = set()
        else:
            Model = self.env[model]
            info = Model.fields_get(attributes=FIELD_ATTRIBUTES)
            names = set(Model._fields)
        definitions = project._studio_field_definitions(model) if project else {}
        for name, (definition, _change) in definitions.items():
            entry = info.setdefault(
                name,
                {
                    "string": definition.get("field_description"),
                    "type": definition.get("ttype"),
                    "relation": definition.get("relation") or False,
                    "selection": definition.get("selection") or [],
                    "required": definition.get("required", False),
                    "readonly": definition.get("readonly", False),
                    "help": definition.get("help") or "",
                    "store": True,
                    # Searched, grouped or added up once Apply creates it.
                    "groupable": False,
                    "searchable": False,
                    "sortable": False,
                    "aggregator": False,
                },
            )
            entry["project"] = True
            entry["pending"] = name not in names
            entry["definition"] = definition
        return info

    @api.model
    def _palette(self, view_type, arch, fields_info):
        """The fields the editor offers to drop: those the view does not
        show yet, that its type can use. A pivot field says on which
        ``axes`` it goes."""
        if view_type == "search":
            shown = {n.get("name") for n in arch.iter("field")}
        else:
            shown = studio_arch.shown_field_names(arch, view_type)
        palette = []
        for name, info in fields_info.items():
            if name in shown or name == "id" or name.startswith("__"):
                continue
            item = {
                "name": name,
                "string": info.get("string") or name,
                "type": info.get("type"),
            }
            if view_type == "search" and not info.get("searchable"):
                continue
            if view_type == "pivot":
                axes = ["row", "col"] if info.get("groupable") else []
                if self._measurable(info):
                    axes.append("measure")
                if not axes:
                    continue
                item["axes"] = axes
            palette.append(item)
        return sorted(palette, key=lambda f: (f["string"] or "").lower())

    @api.model
    def _measurable(self, info):
        return bool(
            info.get("type") in studio_arch.NUMBER_TYPES and info.get("aggregator")
        )

    @api.model
    def _choices(self, fields_info):
        """The values the editor offers for each kind of attribute value
        (see ``SETTABLE_ATTRIBUTES``): [[value, label]] lists. A field of
        the project not yet applied is in none of them."""

        def fields_where(predicate):
            items = [
                [name, info.get("string") or name]
                for name, info in fields_info.items()
                if not info.get("pending") and predicate(info)
            ]
            return sorted(items, key=lambda item: (item[1] or "").lower())

        def stored(types):
            return lambda f: f.get("type") in types and f.get("store")

        return {
            "group_field": fields_where(lambda f: f.get("groupable")),
            "relation_group_field": fields_where(
                lambda f: f.get("groupable")
                and f.get("type") in studio_arch.RELATION_TYPES
            ),
            "date_field": fields_where(stored(studio_arch.DATE_TYPES)),
            "number_field": fields_where(stored(("integer", "float"))),
            "measure": fields_where(self._measurable),
            "search_field": fields_where(lambda f: f.get("searchable")),
            "sort_field": fields_where(lambda f: f.get("sortable")),
            "bool": [["True", "True"], ["False", "False"]],
            "axis": [[axis, axis] for axis in studio_arch.PIVOT_AXES],
            "interval": [[i, i] for i in studio_arch.INTERVALS],
            "timeline_mode": [[m, m] for m in studio_arch.TIMELINE_MODES],
            "widget": [[w, w] for w in studio_arch.WIDGETS],
        }

    @api.model
    def _layout(self, view_type, arch):
        """The part of the payload proper to ``view_type``: where its zones
        are in the arch (paths of the blocks)."""
        path = lambda node: studio_arch.node_xpath(arch, node)  # noqa: E731
        root = f"/{arch.tag}"
        loaded = [c.get("name") for c in studio_arch.elements(arch) if c.tag == "field"]
        if view_type == "kanban":
            templates = studio_arch.templates_of(arch)
            card = templates.get("card")
            if card is None:
                card = templates.get("kanban-box")
            return {
                "root": root,
                "card": path(card) if card is not None else False,
                "templates": {name: path(node) for name, node in templates.items()},
                "loaded_fields": loaded,
                "widgets": {k: list(v) for k, v in studio_arch.WIDGETS.items()},
            }
        if view_type == "timeline":
            item = studio_arch.templates_of(arch).get("timeline-item")
            return {
                "root": root,
                "template": path(item) if item is not None else False,
                "loaded_fields": loaded,
                "colors": studio_arch.colors_rules(arch.get("colors")),
                "color_operators": list(studio_arch.COLOR_OPERATORS),
                "color_types": list(studio_arch.COLOR_FIELD_TYPES),
            }
        if view_type == "search":
            kinds = {"fields": [], "filters": [], "group_bys": []}
            for node in arch.iter("field", "filter"):
                if node.tag == "field":
                    kinds["fields"].append(path(node))
                elif studio_arch.group_by_of(node):
                    kinds["group_bys"].append(path(node))
                else:
                    kinds["filters"].append(path(node))
            return {
                "root": root,
                **kinds,
                "operators": {
                    ttype: list(ops)
                    for ttype, ops in studio_arch.SEARCH_OPERATORS.items()
                },
            }
        if view_type == "pivot":
            axes = {axis: [] for axis in studio_arch.PIVOT_AXES}
            others = []
            for node in studio_arch.elements(arch):
                if node.tag != "field":
                    continue
                axis = node.get("type")
                (axes[axis] if axis in axes else others).append(path(node))
            return {"root": root, "axes": axes, "others": others}
        return {"root": root}

    @api.model
    def get_editor_data(
        self, model, view_id, view_type, project_id=False, pick_project=True
    ):
        """The editor payload of a view: the blocks of its draft arch, the
        fields of the model, the changes of the project and its projects,
        and what its view type allows (operations, attributes, layout).
        ``pick_project``: see ``_project``."""
        self._check_studio_access()
        Project = self.env["erplibre.studio.project"]
        project = self._project(project_id, pick_project, model)
        view = self._resolve_view(model, view_id, view_type, project)
        if project:
            arch, errors = project._draft_arch(view)
        else:
            arch, errors = view._get_combined_arch(), {}
        fields_info = self._fields_payload(model, project)
        changes = []
        if project:
            for change in project._view_changes(view):
                changes.append(
                    {
                        "id": change.id,
                        "type": change.change_type,
                        "summary": change.summary,
                        "xpath": change.xpath,
                        "error": errors.get(change.id) or False,
                    }
                )
        pending = is_pending_view(view)
        if pending:
            sample = False
            model_name = view.line.name
            view_types = list(studio_arch.MODEL_VIEW_TYPES)
        else:
            Model = self.env[model]
            sample = Model.search([], limit=1).id if view.type == "form" else False
            model_name = self.env["ir.model"]._get(model).name
            view_types = list(Project._view_types())
        return {
            "model": model,
            "model_name": model_name,
            "view_type": view.type,
            "view_types": view_types,
            "view": {
                "id": view.id,
                "name": view.name,
                "xml_id": view.xml_id or False,
                "pending": pending,
                "model_line_id": view.line.id if pending else False,
            },
            "blocks": studio_arch.arch_blocks(arch, view.type, fields_info),
            "layout": self._layout(view.type, arch),
            "operations": [
                op
                for op in studio_arch.VIEW_OPERATIONS[view.type]
                if not pending or op in PENDING_VIEW_OPERATIONS.get(view.type, ())
            ],
            "hide_mode": studio_arch.hide_mode(view.type),
            "settable": studio_arch.SETTABLE_ATTRIBUTES.get(view.type, {}),
            "required_attributes": {
                tag: list(names)
                for (vtype, tag), names in studio_arch.REQUIRED_ATTRIBUTES.items()
                if vtype == view.type
            },
            "choices": self._choices(fields_info),
            "fields": fields_info,
            "palette": self._palette(view.type, arch, fields_info),
            "field_types": list(NEW_FIELD_TYPES),
            "changes": changes,
            "errors": [e for e in errors.values()],
            "project": self._project_payload(project) if project else False,
            "projects": [
                {
                    "id": p.id,
                    "name": p.name,
                    "module_name": p.module_name,
                    "state": p.state,
                }
                for p in Project.search([])
            ],
            "preview_key": PREVIEW_KEY,
            "sample_res_id": sample or False,
            "mail_available": Project._studio_mail_available(),
        }

    @api.model
    def _project_payload(self, project):
        """The project as the editor shows it; ``state_label`` is the label
        of its state in the language of the user. ``app`` is its first app,
        for an editor of a single app."""
        states = dict(project._fields["state"]._description_selection(self.env))
        first = project.app_ids[:1]
        pending_models = project.new_model_ids.filtered(lambda m: not m.applied)
        approver = project.approved_uid
        return {
            "id": project.id,
            "name": project.name,
            "module_name": project.module_name,
            "state": project.state,
            "state_label": states.get(project.state, project.state),
            "revision": project.draft_revision,
            "preview_value": f"{project.id}:{project.draft_revision}",
            "change_count": project.change_count,
            "item_count": project.item_count,
            "applied": bool(project.applied_snapshot),
            "app": (
                {"name": first.name, "icon": first.icon or False} if first else False
            ),
            "apps": [self._app_payload(app) for app in project.app_ids],
            "groups": [self._group_payload(group) for group in project.group_line_ids],
            "models": [self._model_payload(line) for line in project.new_model_ids],
            # The menus Apply made, as the web client shows them: when they
            # change, the editor reloads the menus of the web client.
            "menus": [
                [menu.id, menu.name, menu.web_icon or False, menu.parent_id.id]
                for menu in project.created_menu_ids.sudo().sorted("id")
            ],
            "access": [self._access_payload(line) for line in project.access_line_ids],
            "rules": [self._rule_payload(rule) for rule in project.rule_line_ids],
            "approved": project.approved,
            "approved_by": [approver.id, approver.name] if approver else False,
            "approved_date": (
                fields.Datetime.to_string(project.approved_date)
                if project.approved_date
                else False
            ),
            "real_preview_available": bool(project.approved and pending_models),
        }

    @api.model
    def _app_payload(self, app):
        return {
            "id": app.id,
            "name": app.name,
            "icon": app.icon or False,
            "xml_name": app.xml_name,
            "menu_sequence": app.menu_sequence,
            "sequence": app.sequence,
            "applied": app.applied,
            "models": app.model_line_ids.ids,
            "groups": app.group_line_ids.ids,
            "chain": app._studio_chain(),
        }

    @api.model
    def _group_payload(self, group):
        return {
            "id": group.id,
            "app_id": group.app_id.id,
            "name": group.name,
            "xml_name": group.xml_name,
            "comment": group.comment or "",
            "implied": [[g.id, g.name] for g in group.implied_line_ids],
            "implied_groups": [
                [g.id, g.full_name] for g in group.implied_group_ids.sudo()
            ],
            "missing_implied": group._studio_missing_implied_refs(),
            "applied": group.applied,
        }

    @api.model
    def _access_payload(self, line):
        item = {
            "id": line.id,
            "model": line.model,
            "group": (
                [line.group_id.id, line.group_id.full_name] if line.group_id else False
            ),
            **{perm: line[perm] for perm in PERMS},
        }
        if line.group_line_id:
            group = line.group_line_id
            item["group_line"] = [group.id, f"{group.app_id.name} / {group.name}"]
        return item

    @api.model
    def _rule_payload(self, rule):
        return {
            "id": rule.id,
            "name": rule.name,
            "model": rule.model,
            "domain": rule.domain_force,
            "groups": [[g.id, g.full_name] for g in rule.group_ids],
            "group_lines": [
                [g.id, f"{g.app_id.name} / {g.name}"] for g in rule.group_line_ids
            ],
            "global_rule": rule.global_rule,
            "missing_groups": rule._studio_missing_group_refs(),
            **{perm: rule[perm] for perm in PERMS},
        }

    @api.model
    def _model_payload(self, line):
        """A model line as the editor shows it; ``views`` holds the ids of
        its default views once applied; ``pending_views`` says which default
        views hold changes recorded before Apply."""
        views = line._studio_views() if line.applied else {}
        parent = line.menu_parent_id
        changes = line.project_id.change_ids.filtered(lambda c: c.model_line_id == line)
        return {
            "id": line.id,
            "model": line.model,
            "name": line.name,
            "chatter": line.chatter,
            "menu_mode": line.menu_mode,
            "app_id": line.app_id.id,
            "menu_parent": [parent.id, parent.complete_name] if parent else False,
            "menu_name": line.menu_name or "",
            "applied": line.applied,
            "views": {view_type: view.id for view_type, view in views.items()},
            "pending_views": {
                view_type: bool(
                    changes.filtered(lambda c, t=view_type: c.view_type == t)
                )
                for view_type in studio_arch.MODEL_VIEW_TYPES
            },
        }

    @api.model
    def create_project(self, name, module_name):
        """A new project, edited by the user. Return its id."""
        self._check_studio_access()
        project = self.env["erplibre.studio.project"].create(
            {"name": name, "module_name": module_name, "user_id": self.env.uid}
        )
        return project.id

    @api.model
    def _edited_project(self, project_id, revision):
        """The project of an editor call. ``revision`` is the draft revision
        the editor shows: an operation built on another one would locate
        its nodes in a draft that is no longer there."""
        project = self._project(project_id)
        if not project:
            raise UserError(self.env._("Choose or create a studio project first."))
        if revision is not None and int(revision) != project.draft_revision:
            raise UserError(
                self.env._(
                    "The draft of the project changed since this page "
                    "loaded it: reload the editor."
                )
            )
        return project

    @api.model
    def apply_operation(
        self, project_id, model, view_id, view_type, operation, revision=None
    ):
        """Record ``operation`` on the draft; return the new payload.
        ``revision``: see ``_edited_project``."""
        self._check_studio_access()
        project = self._edited_project(project_id, revision)
        view = self._resolve_view(model, view_id, view_type, project)
        project._apply_operation(view, operation or {})
        return self.get_editor_data(model, view.id, view_type, project.id)

    @api.model
    def project_action(
        self,
        project_id,
        action,
        model,
        view_id,
        view_type,
        revision=None,
        fallback=None,
        digest=None,
    ):
        """Run ``action`` (apply, discard, revert, undo, approve, unapprove)
        on the project; return the new payload, with the ``notice`` of the
        action when it answered a notification. ``digest``: the digest of
        the report the user confirmed, for Apply and Revert. When the action
        removed the model or the view on screen (a model of the project),
        the payload is the one of ``fallback`` ([model, view id, view type],
        the view the editor was opened on) with ``view_changed``; without
        such a view left, only {view_gone, project, notice}. A view of a
        model not created yet that Apply created is answered as the view it
        became."""
        self._check_studio_access()
        if action not in PROJECT_ACTIONS:
            raise UserError(self.env._("Unknown action %(action)s.", action=action))
        project = self._edited_project(project_id, revision)
        view = self._resolve_view(model, view_id, view_type, project)
        if action == "action_undo":
            result = project.action_undo(view)
        elif action in DIGEST_ACTIONS:
            result = getattr(project, action)(digest=digest)
        else:
            result = getattr(project, action)()
        if is_pending_view(view):
            alive = model in self.env or bool(project._studio_pending_line(model))
            view_id = False
        else:
            alive = model in self.env and bool(view.exists())
            view_id = view.id
        if alive:
            data = self.get_editor_data(model, view_id, view_type, project.id)
        else:
            data = self._fallback_data(project, fallback)
        if isinstance(result, dict) and result.get("tag") == "display_notification":
            data["notice"] = result["params"]["message"]
        return data

    @api.model
    def _fallback_data(self, project, fallback):
        """The payload of the view ``fallback`` [model, view id, view type]
        flagged ``view_changed``, or {view_gone, project} when it is gone
        too."""
        model, view_id, view_type = (list(fallback or []) + [False] * 3)[:3]
        if model and (model in self.env or project._studio_pending_line(model)):
            try:
                data = self.get_editor_data(
                    model, view_id, view_type or "form", project.id
                )
                data["view_changed"] = True
                return data
            except UserError:
                pass
        return {"view_gone": True, "project": self._project_payload(project)}

    @api.model
    def _registry_models(self):
        """[[model, name]] of the models of the registry that store records."""
        records = self.env["ir.model"].sudo().search([("transient", "=", False)])
        return [
            [r.model, r.name]
            for r in records
            if r.model in self.env and not self.env[r.model]._abstract
        ]

    @api.model
    def _pending_models(self, project_id):
        """[[model, name]] of the models of the project not created yet."""
        Project = self.env["erplibre.studio.project"]
        project = Project.browse(int(project_id)).exists() if project_id else Project
        return [
            [line.model, line.name]
            for line in project.new_model_ids
            if line.model not in self.env
        ]

    @api.model
    def get_comodels(self, project_id=False):
        """[[model, name]] of the models a many2one can point to: those of
        the registry, and the models of the project ``project_id`` that
        Apply creates first."""
        self._check_studio_access()
        return self._registry_models() + self._pending_models(project_id)

    # ── models, access rights and rules ─────────────────────────────────

    @api.model
    def get_studio_choices(self, project_id=False):
        """What the dialogs of the models, the access grid and the rules
        offer: the menus a model can go under (with an external id, no
        action, outside the project), the groups (with an external id; then
        the groups of the project, ``project`` true, by ``line_id``), the
        apps of the project and the icons of an app, the models rights can
        name, and the model names a new model cannot take
        (``taken_models``)."""
        self._check_studio_access()
        Project = self.env["erplibre.studio.project"]
        project = Project.browse(int(project_id)).exists() if project_id else Project
        Menu = (
            self.env["ir.ui.menu"].sudo().with_context(**{"ir.ui.menu.full_list": True})
        )
        menus = Menu.search([]) - project.created_menu_ids
        menu_xmlids = menus.get_external_id()
        groups = self.env["res.groups"].sudo().search([])
        group_xmlids = groups.get_external_id()
        return {
            "mail_available": Project._studio_mail_available(),
            "icons": Project._studio_app_icons(),
            "menus": sorted(
                (
                    {
                        "id": menu.id,
                        "name": menu.complete_name,
                        "xml_id": menu_xmlids[menu.id],
                    }
                    for menu in menus
                    if menu_xmlids.get(menu.id) and not menu.action
                ),
                key=lambda m: m["name"].lower(),
            ),
            "groups": sorted(
                (
                    {
                        "id": group.id,
                        "name": group.full_name,
                        "xml_id": group_xmlids[group.id],
                    }
                    for group in groups - project.created_group_ids
                    if group_xmlids.get(group.id)
                ),
                key=lambda g: g["name"].lower(),
            )
            + [
                {
                    "id": False,
                    "line_id": line.id,
                    "name": f"{line.app_id.name} / {line.name}",
                    "xml_id": f"{project.module_name}.{line.xml_name}",
                    "project": True,
                }
                for line in project.group_line_ids
            ],
            "apps": [
                {
                    "id": app.id,
                    "name": app.name,
                    "icon": app.icon or False,
                    "xml_name": app.xml_name,
                }
                for app in project.app_ids
            ],
            "models": [
                item for item in self._registry_models() if not protected_model(item[0])
            ]
            + self._pending_models(project.id),
            "taken_models": sorted(Project._studio_taken_models()),
        }

    @api.model
    def _answer(self, project, model, view_id, view_type, **extra):
        data = self.get_editor_data(model, view_id, view_type, project.id)
        data.update(extra)
        return data

    @api.model
    def create_model(
        self, project_id, values, model, view_id, view_type, revision=None
    ):
        """Add a model to the project (see ``_studio_create_model``); the
        payload of the current view, with ``created_model``."""
        self._check_studio_access()
        project = self._edited_project(project_id, revision)
        view = self._resolve_view(model, view_id, view_type, project)
        line = project._studio_create_model(values or {})
        return self._answer(
            project,
            model,
            view.id,
            view_type,
            created_model=self._model_payload(line),
        )

    @api.model
    def update_model(
        self, project_id, line_id, values, model, view_id, view_type, revision=None
    ):
        self._check_studio_access()
        project = self._edited_project(project_id, revision)
        view = self._resolve_view(model, view_id, view_type, project)
        project._studio_update_model(project._studio_model_line(line_id), values or {})
        return self._answer(project, model, view.id, view_type)

    @api.model
    def remove_model(
        self, project_id, line_id, model, view_id, view_type, revision=None
    ):
        self._check_studio_access()
        project = self._edited_project(project_id, revision)
        view = self._resolve_view(model, view_id, view_type, project)
        project._studio_remove_model(project._studio_model_line(line_id))
        return self._answer(project, model, view.id, view_type)

    @api.model
    def update_app(self, project_id, values, model, view_id, view_type, revision=None):
        """Rename the first app of the project or change its icon (an editor
        of a single app); ``save_app`` edits any app."""
        self._check_studio_access()
        project = self._edited_project(project_id, revision)
        view = self._resolve_view(model, view_id, view_type, project)
        project._studio_update_app(values or {})
        return self._answer(project, model, view.id, view_type)

    @api.model
    def set_access(self, project_id, rows, model, view_id, view_type, revision=None):
        """Replace the access rows of the project (``_studio_set_access``)."""
        self._check_studio_access()
        project = self._edited_project(project_id, revision)
        view = self._resolve_view(model, view_id, view_type, project)
        project._studio_set_access(rows or [])
        return self._answer(project, model, view.id, view_type)

    @api.model
    def save_rule(self, project_id, rule, model, view_id, view_type, revision=None):
        """Create or update a rule of the project (``_studio_save_rule``)."""
        self._check_studio_access()
        project = self._edited_project(project_id, revision)
        view = self._resolve_view(model, view_id, view_type, project)
        line = project._studio_save_rule(rule or {})
        return self._answer(project, model, view.id, view_type, saved_rule=line.id)

    @api.model
    def remove_rule(
        self, project_id, rule_id, model, view_id, view_type, revision=None
    ):
        self._check_studio_access()
        project = self._edited_project(project_id, revision)
        view = self._resolve_view(model, view_id, view_type, project)
        project._studio_remove_rule(project._studio_rule_line(rule_id))
        return self._answer(project, model, view.id, view_type)

    @api.model
    def check_rule_domain(self, project_id, model, domain):
        """{ok, count} when ``domain`` applies to ``model`` as a record
        rule, ``count`` the records it matches (False for a model not
        created yet); else {ok: False, error}."""
        self._check_studio_access()
        # A read: the project is not opened, its editor and its revision
        # stay as they are.
        Project = self.env["erplibre.studio.project"]
        project = Project.browse(int(project_id or 0)).exists()
        if not project:
            raise UserError(self.env._("Choose or create a studio project first."))
        try:
            project._studio_check_rights_model(model)
            terms = project._studio_rule_domain(model, domain)
        except UserError as exc:
            return {"ok": False, "error": str(exc.args[0])}
        count = False
        if model in self.env:
            count = self.env[model].sudo().search_count(terms)
        return {"ok": True, "count": count}

    @api.model
    def get_access_existing(self, project_id, model):
        """The access rights of ``model`` the project did not create:
        [{id, name, group, perm_*, module}], to show next to its grid."""
        self._check_studio_access()
        Project = self.env["erplibre.studio.project"]
        project = Project.browse(int(project_id)).exists() if project_id else Project
        if model not in self.env:
            return []
        rows = (
            self.env["ir.model.access"].sudo().search([("model_id.model", "=", model)])
            - project.created_access_ids
        )
        xmlids = rows.get_external_id()
        return [
            {
                "id": row.id,
                "name": row.name,
                "group": (
                    [row.group_id.id, row.group_id.full_name] if row.group_id else False
                ),
                "module": (xmlids.get(row.id) or "").split(".")[0] or False,
                **{perm: row[perm] for perm in PERMS},
            }
            for row in rows
        ]

    # ── apps and groups ─────────────────────────────────────────────────

    @api.model
    def save_app(self, project_id, values, model, view_id, view_type, revision=None):
        """Create or update an app of the project (``_studio_save_app``); the
        payload with ``saved_app``."""
        self._check_studio_access()
        project = self._edited_project(project_id, revision)
        view = self._resolve_view(model, view_id, view_type, project)
        app = project._studio_save_app(values or {})
        return self._answer(project, model, view.id, view_type, saved_app=app.id)

    @api.model
    def remove_app(self, project_id, app_id, model, view_id, view_type, revision=None):
        """Remove an app of the project: refused while a model or a group
        goes in it."""
        self._check_studio_access()
        project = self._edited_project(project_id, revision)
        view = self._resolve_view(model, view_id, view_type, project)
        project._studio_remove_app(project._studio_app_line(app_id))
        return self._answer(project, model, view.id, view_type)

    @api.model
    def save_group(self, project_id, values, model, view_id, view_type, revision=None):
        """Create or update a group of the project (``_studio_save_group``);
        the payload with ``saved_group``."""
        self._check_studio_access()
        project = self._edited_project(project_id, revision)
        view = self._resolve_view(model, view_id, view_type, project)
        group = project._studio_save_group(values or {})
        return self._answer(project, model, view.id, view_type, saved_group=group.id)

    @api.model
    def remove_group(
        self, project_id, group_id, model, view_id, view_type, revision=None
    ):
        """Remove a group of the project with its access rows; the rules and
        the groups that named it lose it."""
        self._check_studio_access()
        project = self._edited_project(project_id, revision)
        view = self._resolve_view(model, view_id, view_type, project)
        project._studio_remove_group(project._studio_group_line(group_id))
        return self._answer(project, model, view.id, view_type)

    # ── relations ───────────────────────────────────────────────────────

    @api.model
    def get_relation_choices(
        self, project_id, model, comodel, ttype="one2many", label=None
    ):
        """What the dialog of a new one2many or many2many of ``model`` to
        ``comodel`` offers: {inverses: [{name, label, pending}],
        inverse_name, inverse_label, on_delete, protected} for a one2many
        (the inverse many2one to choose, else the one the studio creates),
        {relation_table, column1, column2} for a many2many labelled
        ``label``. A read."""
        self._check_studio_access()
        project = self._read_project(project_id)
        known = model in self.env or project._studio_pending_line(model)
        if not known:
            raise UserError(self.env._("Unknown model %(model)s.", model=model))
        comodel = project._clean_relation({"relation": comodel})
        if ttype == "many2many":
            table, column1, column2 = studio_arch.many2many_names(
                project.module_name,
                model,
                comodel,
                project._studio_proposed_field_name(model, comodel, label),
                project._studio_relation_table_names(),
            )
            return {
                "relation_table": table,
                "column1": column1,
                "column2": column2,
            }
        name, label = project._studio_proposed_inverse(model, comodel)
        return {
            "inverses": project._studio_inverse_choices(model, comodel),
            "inverse_name": name,
            "inverse_label": label,
            "on_delete": (
                "cascade" if comodel in project._studio_new_models() else "set null"
            ),
            "protected": protected_model(comodel),
        }

    # ── confirmations ───────────────────────────────────────────────────

    @api.model
    def get_revert_report(self, project_id):
        """{report, digest, refused}: what Revert removes, the digest Revert
        then asks, and why it is refused (or False). A read."""
        self._check_studio_access()
        return self._read_project(project_id)._studio_revert_report()

    @api.model
    def get_apply_report(self, project_id):
        """{report, digest, confirm}: what Apply removes; ``confirm`` when it
        holds records, values or group members, and Apply then asks the
        digest. A read."""
        self._check_studio_access()
        return self._read_project(project_id)._studio_apply_report()

    # ── preview of a model not created yet ──────────────────────────────

    @api.model
    def get_model_preview(
        self, project_id, line_id, view_type="form", mode="simulation"
    ):
        """The preview of the model line ``line_id``, not created yet, in the
        shape of get_views: « simulation » computes it from the draft and
        writes nothing; « real », once the project is approved, renders it
        from the model created in a savepoint, then rolled back. Not a
        readonly call: the real mode needs a cursor that writes."""
        self._check_studio_access()
        if mode not in PREVIEW_MODES:
            raise UserError(self.env._("Unknown preview mode %(mode)s.", mode=mode))
        if view_type not in studio_arch.MODEL_VIEW_TYPES:
            raise UserError(
                self.env._(
                    "Apply the model first: %(type)s needs its records.",
                    type=view_type,
                )
            )
        project = self._read_project(project_id)
        line = project._studio_model_line(line_id)
        if line.applied:
            raise UserError(
                self.env._(
                    "The model %(model)s exists: its preview is the one of its "
                    "views.",
                    model=line.model,
                )
            )
        if mode == "real":
            data = project._studio_real_views(line)
        else:
            data = project._studio_simulated_views(line)
        data["view_type"] = view_type
        return data
