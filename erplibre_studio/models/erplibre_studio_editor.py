# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, models
from odoo.exceptions import UserError

from .. import arch as studio_arch
from .erplibre_studio_project import NEW_FIELD_TYPES, PREVIEW_KEY

FIELD_ATTRIBUTES = [
    "string",
    "type",
    "required",
    "readonly",
    "relation",
    "selection",
    "help",
    "store",
]

PROJECT_ACTIONS = (
    "action_apply",
    "action_discard",
    "action_revert",
    "action_undo",
)


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
    def _resolve_view(self, model, view_id, view_type):
        """The primary view the editor inherits: ``view_id``, or the default
        view of ``model`` for ``view_type``."""
        if view_type not in studio_arch.VIEW_TYPES:
            raise UserError(self.env._("The studio edits form and list views only."))
        if model not in self.env:
            raise UserError(self.env._("Unknown model %(model)s.", model=model))
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
    def _project(self, project_id, pick_project=True):
        """The project ``project_id``; without one, the last project of the
        user unless ``pick_project`` is False. Opening a project makes the
        user its editor, the one who sees its draft."""
        Project = self.env["erplibre.studio.project"]
        project = Project.browse(int(project_id)).exists() if project_id else Project
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
        """The client action of the editor on a view."""
        self._check_studio_access()
        view = self._resolve_view(model, view_id, view_type)
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
        Model = self.env[model]
        info = Model.fields_get(attributes=FIELD_ATTRIBUTES)
        for change in project._project_field_changes(model) if project else []:
            definition = change._payload().get("field") or {}
            entry = info.setdefault(
                change.field_name,
                {
                    "string": definition.get("field_description"),
                    "type": definition.get("ttype"),
                    "relation": definition.get("relation") or False,
                    "selection": definition.get("selection") or [],
                    "required": definition.get("required", False),
                    "readonly": definition.get("readonly", False),
                    "help": definition.get("help") or "",
                    "store": True,
                },
            )
            entry["project"] = True
            entry["pending"] = change.field_name not in Model._fields
            entry["definition"] = definition
        return info

    @api.model
    def get_editor_data(
        self, model, view_id, view_type, project_id=False, pick_project=True
    ):
        """The editor payload of a view: the blocks of its draft arch, the
        fields of the model, the changes of the project and its projects.
        ``pick_project``: see ``_project``."""
        self._check_studio_access()
        view = self._resolve_view(model, view_id, view_type)
        project = self._project(project_id, pick_project)
        Project = self.env["erplibre.studio.project"]
        if project:
            arch, errors = project._draft_arch(view)
        else:
            arch, errors = view._get_combined_arch(), {}
        fields_info = self._fields_payload(model, project)
        in_view = studio_arch.arch_field_names(arch)
        palette = sorted(
            (
                {
                    "name": name,
                    "string": f.get("string") or name,
                    "type": f.get("type"),
                }
                for name, f in fields_info.items()
                if name not in in_view and name != "id" and not name.startswith("__")
            ),
            key=lambda f: (f["string"] or "").lower(),
        )
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
        Model = self.env[model]
        sample = Model.search([], limit=1).id if view_type == "form" else False
        return {
            "model": model,
            "model_name": self.env["ir.model"]._get(model).name,
            "view_type": view.type,
            "view": {
                "id": view.id,
                "name": view.name,
                "xml_id": view.xml_id or False,
            },
            "blocks": studio_arch.arch_blocks(arch, view.type, fields_info),
            "fields": fields_info,
            "palette": palette,
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
        }

    @api.model
    def _project_payload(self, project):
        """The project as the editor shows it; ``state_label`` is the label
        of its state in the language of the user."""
        states = dict(project._fields["state"]._description_selection(self.env))
        return {
            "id": project.id,
            "name": project.name,
            "module_name": project.module_name,
            "state": project.state,
            "state_label": states.get(project.state, project.state),
            "revision": project.draft_revision,
            "preview_value": f"{project.id}:{project.draft_revision}",
            "change_count": project.change_count,
            "applied": bool(project.applied_snapshot),
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
        view = self._resolve_view(model, view_id, view_type)
        project = self._edited_project(project_id, revision)
        project._apply_operation(view, operation or {})
        return self.get_editor_data(model, view.id, view_type, project.id)

    @api.model
    def project_action(
        self, project_id, action, model, view_id, view_type, revision=None
    ):
        """Run ``action`` (apply, discard, revert, undo) on the project;
        return the new payload, with the ``notice`` of the action when it
        answered a notification."""
        self._check_studio_access()
        if action not in PROJECT_ACTIONS:
            raise UserError(self.env._("Unknown action %(action)s.", action=action))
        view = self._resolve_view(model, view_id, view_type)
        project = self._edited_project(project_id, revision)
        if action == "action_undo":
            result = project.action_undo(view)
        else:
            result = getattr(project, action)()
        data = self.get_editor_data(model, view.id, view_type, project.id)
        if isinstance(result, dict) and result.get("tag") == "display_notification":
            data["notice"] = result["params"]["message"]
        return data

    @api.model
    def get_comodels(self):
        """[[model, name]] of the models a many2one can point to."""
        self._check_studio_access()
        records = self.env["ir.model"].sudo().search([("transient", "=", False)])
        return [
            [r.model, r.name]
            for r in records
            if r.model in self.env and not self.env[r.model]._abstract
        ]
