# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from .. import arch as studio_arch
from .erplibre_studio_project import NO_TOUCH_KEY, RESTORE_KEY, SERVER_VALUES

MENU_MODES = [
    ("app", "In the app of the project"),
    ("menu", "Under a menu"),
]


class ErplibreStudioLine(models.AbstractModel):
    """What the lines of a project share: a line written from outside the
    editor operations (the project form, an RPC call) is a change of the
    draft, as a change of a view is, under the guard of the editor
    (Settings group and developer mode). Server code in sudo skips it: it
    passed that guard itself."""

    _name = "erplibre.studio.line"
    _description = "ERPLibre studio project line"

    project_id = fields.Many2one(
        "erplibre.studio.project",
        required=True,
        ondelete="cascade",
        index=True,
    )

    def _touch_projects(self, projects):
        if not self.env.context.get(NO_TOUCH_KEY):
            projects.exists()._touch()

    def _check_line_access(self):
        if not self.env.su:
            self.env["erplibre.studio.project"]._check_studio_access()

    @api.model
    def _server_fields(self):
        """The fields of the line that the server computes: a value sent by
        a client is dropped."""
        return set()

    def _drop_server_fields(self, vals):
        if self.env.context.get(RESTORE_KEY) is SERVER_VALUES:
            return vals
        return {k: v for k, v in vals.items() if k not in self._server_fields()}

    def _server_writing(self):
        """The lines as the server writes their computed fields."""
        return self.with_context(**{RESTORE_KEY: SERVER_VALUES})

    @api.model_create_multi
    def create(self, vals_list):
        self._check_line_access()
        vals_list = [self._drop_server_fields(vals) for vals in vals_list]
        lines = super().create(vals_list)
        self._touch_projects(lines.project_id)
        return lines

    def write(self, vals):
        self._check_line_access()
        vals = self._drop_server_fields(vals)
        projects = self.project_id
        res = super().write(vals)
        self._touch_projects(projects | self.project_id)
        return res

    def unlink(self):
        self._check_line_access()
        projects = self.project_id
        res = super().unlink()
        self._touch_projects(projects)
        return res

    @api.model
    def _underscored(self, name):
        """``name`` (a model, an external id) with its dots as underscores,
        for the name of an external id."""
        return (name or "").replace(".", "_")


class ErplibreStudioModel(models.Model):
    """A model the project creates: Apply makes it a custom model with a
    ``x_name``, a form, a list and a search view, a window action and a
    menu, all under external ids of the module of the project."""

    _name = "erplibre.studio.model"
    _inherit = "erplibre.studio.line"
    _description = "ERPLibre studio model"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    model = fields.Char(
        string="Technical name",
        required=True,
        help="x_ then lower case letters, digits and underscores; it "
        "cannot change once applied.",
    )
    name = fields.Char(string="Label", required=True)
    chatter = fields.Boolean(
        help="Messages, followers and activities on the records (mail). "
        "Once applied, the chatter cannot be removed.",
    )
    menu_mode = fields.Selection(MENU_MODES, required=True, default="app")
    menu_parent_id = fields.Many2one(
        "ir.ui.menu",
        string="Parent menu",
        ondelete="set null",
        help="The menu the menu of the model goes under, with « Under a menu ».",
    )
    menu_name = fields.Char(help="The label of the menu; empty: the label.")
    menu_sequence = fields.Integer(default=10)
    applied = fields.Boolean(compute="_compute_applied")
    ir_model_id = fields.Many2one(
        "ir.model", compute="_compute_applied", string="Model in the database"
    )

    _sql_constraints = [
        (
            "model_uniq",
            "unique(model)",
            "Another studio project creates this model.",
        ),
    ]

    # ── external ids ────────────────────────────────────────────────────

    def _studio_xml_names(self):
        """The names, under the module of the project, of the external ids
        of what Apply makes for the model: ``model`` (the ir.model, as Odoo
        names it when a module defines it), ``form`` / ``list`` / ``search``
        (the primary views), ``action`` and ``menu``."""
        self.ensure_one()
        name = self._underscored(self.model)
        names = {
            "model": f"model_{name}",
            "action": f"action_{name}",
            "menu": f"menu_{name}",
        }
        for view_type in studio_arch.MODEL_VIEW_TYPES:
            names[view_type] = f"view_{name}_{view_type}"
        return names

    @api.depends("model", "project_id.module_name")
    def _compute_applied(self):
        for line in self:
            record = line.project_id._studio_record(
                "ir.model", line._studio_xml_names()["model"]
            )
            line.ir_model_id = record
            line.applied = bool(record) and record.model in self.env

    def _studio_views(self):
        """{view type: primary view} of the applied model."""
        self.ensure_one()
        names = self._studio_xml_names()
        views = {}
        for view_type in studio_arch.MODEL_VIEW_TYPES:
            view = self.project_id._studio_record("ir.ui.view", names[view_type])
            if view:
                views[view_type] = view
        return views

    def _snapshot(self):
        return [
            {
                "model": line.model,
                "name": line.name,
                "chatter": line.chatter,
                "menu_mode": line.menu_mode,
                "menu_parent_id": line.menu_parent_id.id,
                "menu_name": line.menu_name or "",
                "menu_sequence": line.menu_sequence,
                "sequence": line.sequence,
            }
            for line in self.sorted(lambda m: (m.sequence, m.model))
        ]

    # ── constraints ─────────────────────────────────────────────────────

    @api.constrains("model", "name")
    def _check_studio_model(self):
        Line = self.env["erplibre.studio.model"].sudo()
        for line in self:
            if not studio_arch.valid_model_name(line.model):
                raise ValidationError(
                    self.env._(
                        "%(name)s is not a valid model name: x_ then a "
                        "letter, then lower case letters, digits and "
                        "underscores, %(size)s characters at most.",
                        name=line.model,
                        size=studio_arch.MODEL_NAME_SIZE,
                    )
                )
            if line.model in self.env and not line.applied:
                raise ValidationError(
                    self.env._("The model %(name)s already exists.", name=line.model)
                )
            if Line.search_count([("model", "=", line.model), ("id", "!=", line.id)]):
                raise ValidationError(
                    self.env._(
                        "Another studio project creates the model %(name)s.",
                        name=line.model,
                    )
                )
            label = (line.name or "").strip()
            if not label:
                raise ValidationError(self.env._("A model needs a label."))
            line.project_id._check_field_texts(label, "")

    @api.constrains("chatter")
    def _check_studio_chatter(self):
        for line in self:
            if not line.chatter:
                record = line.ir_model_id
                if line.applied and "is_mail_thread" in record._fields:
                    if record.is_mail_thread:
                        raise ValidationError(
                            self.env._(
                                "The chatter of %(name)s cannot be removed "
                                "once applied.",
                                name=line.model,
                            )
                        )
            elif not line.project_id._studio_mail_available():
                raise ValidationError(
                    self.env._("A chatter needs the module mail (Discuss).")
                )

    @api.constrains("menu_mode", "menu_parent_id")
    def _check_studio_menu(self):
        for line in self:
            line.project_id._studio_check_menu(line)

    # ── writes ──────────────────────────────────────────────────────────

    def write(self, vals):
        """A new technical name, before Apply, moves the access rows, the
        rules and the new many2one of the project with it."""
        renamed = {}
        if "model" in vals:
            for line in self:
                if vals["model"] == line.model:
                    continue
                if line.applied:
                    raise UserError(
                        self.env._(
                            "The technical name of the model %(name)s cannot "
                            "change once applied.",
                            name=line.model,
                        )
                    )
                renamed[line] = line.model
        if not renamed:
            return super().write(vals)
        projects = self.project_id
        res = super(
            ErplibreStudioModel, self.with_context(**{NO_TOUCH_KEY: True})
        ).write(vals)
        for line, old in renamed.items():
            project = line.project_id.with_context(**{NO_TOUCH_KEY: True})
            project.access_line_ids.filtered(lambda a: a.model == old).write(
                {"model": line.model}
            )
            project.rule_line_ids.filtered(lambda r: r.model == old).write(
                {"model": line.model}
            )
            for change in project._project_field_changes():
                payload = change._payload()
                if (payload.get("field") or {}).get("relation") == old:
                    payload["field"]["relation"] = line.model
                    change._set_payload(payload)
        self._touch_projects(projects | self.project_id)
        return res

    def unlink(self):
        """A model leaves the project with what names it: its access and
        rule lines, the changes of its views, the new fields on it or
        pointing at it, and the changes of the project that show these
        fields or depend on the nodes they add."""
        for line in self:
            project = line.project_id
            project.access_line_ids.filtered(lambda a: a.model == line.model).unlink()
            project.rule_line_ids.filtered(lambda r: r.model == line.model).unlink()
            pointing = project.change_ids.filtered(
                lambda c: c.change_type == "add_field"
                and (c._payload().get("field") or {}).get("relation") == line.model
            )
            names = {}
            for change in pointing:
                names.setdefault(change.model, set()).add(change.field_name)
            (
                project.change_ids.filtered(lambda c: c.model == line.model)
                | project._studio_changes_of_fields(names)
            ).unlink()
        return super().unlink()

    @api.model
    def _studio_line_vals(self, item):
        """The values of a line from ``item``, one entry of ``_snapshot``."""
        return {
            key: item.get(key)
            for key in (
                "model",
                "name",
                "chatter",
                "menu_mode",
                "menu_name",
                "menu_sequence",
                "sequence",
            )
        } | {"menu_parent_id": item.get("menu_parent_id") or False}
