# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import ast

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from .. import arch as studio_arch
from .erplibre_studio_project import (
    NO_TOUCH_KEY,
    RESTORE_KEY,
    SERVER_VALUES,
    check_studio_write,
    protected_model,
)

MENU_MODES = [
    ("app", "In an app of the project"),
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
        check_studio_write(self.env)

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
        help="Lower case letters, digits, underscores and dots; x_ first "
        "unless the database allows otherwise; it cannot change once applied.",
    )
    name = fields.Char(string="Label", required=True)
    chatter = fields.Boolean(
        help="Messages, followers and activities on the records (mail). "
        "Once applied, the chatter cannot be removed.",
    )
    menu_mode = fields.Selection(MENU_MODES, required=True, default="app")
    app_id = fields.Many2one(
        "erplibre.studio.app",
        string="App",
        ondelete="set null",
        help="The app of the project the menu of the model goes in, with « In "
        "an app of the project ».",
    )
    menu_parent_id = fields.Many2one(
        "ir.ui.menu",
        string="Parent menu",
        ondelete="set null",
        help="The menu the menu of the model goes under, with « Under a menu ».",
    )
    menu_name = fields.Char(help="The label of the menu; empty: the label.")
    menu_sequence = fields.Integer(default=10)
    order = fields.Char(
        string="Default order",
        help="How the lists sort the records, « field asc » or « field desc » "
        "terms separated by commas; empty: the order of creation.",
    )
    archivable = fields.Boolean(
        help="The records can be archived (the field x_active). Turned off "
        "after Apply, the next Apply removes the field and its values, after "
        "a confirmation.",
    )
    manual_order = fields.Boolean(
        help="The records are ordered by hand, with the handle of the list "
        "(the field x_sequence). Turned off after Apply, the next Apply "
        "removes the field and its values, after a confirmation.",
    )
    per_company = fields.Boolean(
        string="Per company",
        help="Each record belongs to a company (the field x_company_id), and a "
        "global record rule shows a user the records of their companies and "
        "those of no company. Turned off after Apply, the next Apply removes "
        "the field and its values, after a confirmation.",
    )
    company_rule_id = fields.Many2one(
        "erplibre.studio.rule",
        string="Multi-company rule",
        ondelete="set null",
        help="The rule line the option « Per company » created; empty once "
        "the rule is removed from the project.",
    )
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

    @api.model
    def _server_fields(self):
        return super()._server_fields() | {"company_rule_id"}

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
                "app": line.app_id.xml_name or "",
                "menu_parent_id": line.menu_parent_id.id,
                "menu_name": line.menu_name or "",
                "menu_sequence": line.menu_sequence,
                "sequence": line.sequence,
                # Written when set only: the snapshot of a project applied
                # before the options stays equal to its draft.
                **({"order": line.order} if line.order else {}),
                **{key: True for key in studio_arch.MODEL_OPTIONS if line[key]},
                **(
                    {"company_rule": line.company_rule_id.xml_name}
                    if line.company_rule_id
                    else {}
                ),
            }
            for line in self.sorted(lambda m: (m.sequence, m.model))
        ]

    def _studio_option_fields(self):
        """{field name: definition} of the fields the options that are on
        add to the model: {ttype, field_description} and either
        ``default``, a constant as ir.model.fields writes it (a text) that
        Apply stores as an ir.default, or, for a many2one, ``relation``,
        ``on_delete`` and ``default_lambda``, the default of the generated
        class: a company depends on the user, no ir.default holds it."""
        self.ensure_one()
        defaults = {"boolean": "True", "integer": "10"}
        lambdas = {"x_company_id": "lambda self: self.env.company"}
        options = {}
        for key, (name, ttype, label) in studio_arch.MODEL_OPTIONS.items():
            if not self[key]:
                continue
            definition = {"ttype": ttype, "field_description": label}
            if name in studio_arch.MODEL_OPTION_RELATIONS:
                relation, on_delete = studio_arch.MODEL_OPTION_RELATIONS[name]
                definition.update(
                    relation=relation,
                    on_delete=on_delete,
                    default_lambda=lambdas[name],
                )
            else:
                definition["default"] = defaults[ttype]
            options[name] = definition
        return options

    def _studio_option_defaults(self):
        """{field name: default value} of the fields of the options that are
        on and have a constant default, as Python values (ir.default,
        default_get)."""
        return {
            name: ast.literal_eval(definition["default"])
            for name, definition in self._studio_option_fields().items()
            if "default" in definition
        }

    def _studio_option_field_vals(self):
        """{field name: ir.model.fields values} of the fields of the options
        that are on: label and type, and the comodel and the « on delete »
        of a many2one."""
        vals = {}
        for name, definition in self._studio_option_fields().items():
            vals[name] = {
                "name": name,
                "field_description": definition["field_description"],
                "ttype": definition["ttype"],
            }
            if definition.get("relation"):
                vals[name]["relation"] = definition["relation"]
                vals[name]["on_delete"] = definition["on_delete"]
        return vals

    def _studio_action_context(self):
        """The context text of the window action of the model, or False:
        with « Per company », a record created from the action takes the
        current company of the user."""
        self.ensure_one()
        return studio_arch.COMPANY_ACTION_CONTEXT if self.per_company else False

    def _studio_options_applied(self):
        """{option: whether the applied model has its field}: turned off,
        the next Apply removes it when it is the option's own
        (``_studio_option_own_field`` of the project)."""
        self.ensure_one()
        names = set()
        if self.applied:
            names = set(self.ir_model_id.field_id.mapped("name"))
        return {
            key: name in names
            for key, (name, _ttype, _label) in studio_arch.MODEL_OPTIONS.items()
        }

    # ── constraints ─────────────────────────────────────────────────────

    @api.constrains("model", "name")
    def _check_studio_model(self):
        """The technical name of a line not applied follows the rule of the
        database (``_studio_model_name_rule``); an applied line is not
        checked again: its model exists, under a name a former rule
        allowed, and Discard restores it as it is."""
        Line = self.env["erplibre.studio.model"].sudo()
        for line in self:
            if not line.applied:
                line._check_studio_model_name()
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

    def _check_studio_model_name(self):
        """Raise ValidationError when the technical name of the line fails
        a check of ``studio_arch.model_name_refusal`` under the rule of the
        database, names a model that takes no access row
        (``protected_model``), or a model a module on the addons path
        defines (``_studio_reserved_model_names``)."""
        self.ensure_one()
        project = self.project_id
        rule = project._studio_model_name_rule()
        refusal = studio_arch.model_name_refusal(self.model, rule["prefix_required"])
        size = studio_arch.MODEL_NAME_SIZE
        code = refusal.code if refusal is not None else None
        if code == "prefix" or (code == "format" and rule["prefix_required"]):
            raise ValidationError(
                self.env._(
                    "%(name)s is not a valid model name: x_ then a "
                    "letter, then lower case letters, digits and "
                    "underscores, %(size)s characters at most.",
                    name=self.model,
                    size=size,
                )
            )
        if code == "format":
            raise ValidationError(
                self.env._(
                    "%(name)s is not a valid model name: lower case letters, "
                    "digits, underscores and dots, each part starting with a "
                    "letter, %(size)s characters at most.",
                    name=self.model,
                    size=size,
                )
            )
        if refusal is not None or protected_model(self.model):
            raise ValidationError(
                self.env._(
                    "%(name)s is a reserved model name: a Python keyword, a "
                    "namespace of Odoo or a model that takes no access right.",
                    name=self.model,
                )
            )
        if self.model in project._studio_reserved_model_names():
            raise ValidationError(
                self.env._(
                    "A module on the addons path defines %(name)s",
                    name=self.model,
                )
            )

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

    @api.constrains(*studio_arch.MODEL_OPTIONS)
    def _check_studio_options(self):
        """The field of an option on cannot be a new field of the project.
        An option turned off after Apply is accepted: the next Apply removes
        its field (``_studio_option_removals`` of the project)."""
        for line in self:
            definitions = line.project_id._studio_field_definitions(line.model)
            for key, (name, _ttype, _label) in studio_arch.MODEL_OPTIONS.items():
                if line[key] and name in definitions:
                    raise ValidationError(
                        self.env._(
                            "%(field)s is already a new field of %(name)s: "
                            "remove it before turning the option on.",
                            field=name,
                            name=line.model,
                        )
                    )

    @api.constrains("menu_mode", "menu_parent_id", "app_id")
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
            project.change_ids.filtered(lambda c: c.model_line_id == line).write(
                {"model": line.model}
            )
            project.access_line_ids.filtered(lambda a: a.model == old).write(
                {"model": line.model}
            )
            project.rule_line_ids.filtered(lambda r: r.model == old).write(
                {"model": line.model}
            )
            for change in project._project_field_changes():
                payload = change._payload()
                field = payload.get("field") or {}
                if field.get("relation") == old:
                    field["relation"] = line.model
                    change._set_payload(payload)
        self._touch_projects(projects | self.project_id)
        return res

    def unlink(self):
        """A model leaves the project with what names it: the views the
        project adds to it, its access and rule lines, the changes of its
        views, the new fields on it or pointing at it, and the changes of
        the project that show these fields or depend on the nodes they
        add."""
        for line in self:
            project = line.project_id
            project.view_line_ids.filtered(lambda v: v.model == line.model).unlink()
            project.access_line_ids.filtered(lambda a: a.model == line.model).unlink()
            project.rule_line_ids.filtered(lambda r: r.model == line.model).unlink()
            pointing = project.change_ids.filtered(
                lambda c: c.change_type == "add_field"
                and (c._payload().get("field") or {}).get("relation") == line.model
            )
            own = project.change_ids.filtered(lambda c: c.model == line.model)
            names = {}
            for change in pointing | own.filtered(
                lambda c: c.change_type == "add_field"
            ):
                names.setdefault(change.model, set()).add(change.field_name)
                definition = change._payload().get("field") or {}
                inverse = project._studio_inverse_definition(change.model, definition)
                if inverse:
                    names.setdefault(definition["relation"], set()).add(inverse[0])
            (own | project._studio_changes_of_fields(names)).unlink()
        return super().unlink()

    @api.model
    def _studio_line_vals(self, item, project):
        """The values of a line from ``item``, one entry of ``_snapshot``;
        its app is the app of ``project`` of that external id."""
        app = project.app_ids.filtered(lambda a: a.xml_name == item.get("app"))
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
        } | {
            "menu_parent_id": item.get("menu_parent_id") or False,
            "app_id": app[:1].id,
            # A snapshot written before the options, or with an option
            # off, has no key.
            "order": item.get("order") or False,
            **{key: bool(item.get(key)) for key in studio_arch.MODEL_OPTIONS},
        }
