# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import json
import logging
import re

from lxml import etree
from odoo import api, fields, models
from odoo.addons.base.models.ir_module import STATES
from odoo.exceptions import UserError, ValidationError
from odoo.modules.module import get_module_path

from .. import arch as studio_arch

_logger = logging.getLogger(__name__)

# The context key that asks get_views for the draft of a project. The web
# client sends get_views only the « lang » and « *_view_ref » keys of the
# context, and Odoo keys its view cache on them: the suffix is what lets
# the key through. Value: « <project id>:<draft revision> ».
PREVIEW_KEY = "erplibre_studio_view_ref"
# The views of the project left out of a combined arch: the draft replaces
# them. Its value must be a ``ViewExclusion``.
EXCLUDE_KEY = "erplibre_studio_exclude_view_ids"
# Set by the project on its own writes of the fields it manages, together
# with sudo: an RPC call cannot be superuser.
INTERNAL_KEY = "erplibre_studio_internal"
# Set by the project when it changes its changes itself and touches its
# draft once for all of them.
NO_TOUCH_KEY = "erplibre_studio_no_touch"

# The fields of a project only its own methods write; ``_managed_fields``
# adds those of the modules that extend the project.
MANAGED_FIELDS = frozenset(
    {
        "state",
        "draft_revision",
        "applied_snapshot",
        "applied_date",
        "field_ids",
        "studio_view_ids",
    }
)

# Inheriting views apply by priority then id: 99 puts the studio view
# after the views of the modules, as in the draft.
STUDIO_PRIORITY = 99

NEW_FIELD_TYPES = (
    "char",
    "integer",
    "float",
    "boolean",
    "date",
    "datetime",
    "selection",
    "many2one",
    "text",
    "html",
    "monetary",
)

# The fields_get attributes the operations check.
FIELD_INFO = [
    "string",
    "type",
    "store",
    "groupable",
    "searchable",
    "sortable",
    "aggregator",
    "selection",
    "relation",
]


class ViewExclusion(tuple):
    """The ids of the views left out of a combined arch (``EXCLUDE_KEY``).
    A Python type that no RPC call can build: a list sent by a client in
    its context is ignored, so the shared view cache never holds an arch
    without the views of the modules."""


class ErplibreStudioProject(models.Model):
    """A studio project: the changes of views (form, list, kanban, search,
    pivot, timeline) that make one module. Its life: draft changes (previewed by its editor only), then
    applied to the database (``x_`` fields, one inherited view per edited
    view, under external ids of the module ``module_name``). Writing the
    project as a module is the part of erplibre_studio_generate."""

    _name = "erplibre.studio.project"
    _description = "ERPLibre studio project"
    _order = "write_date desc, id desc"

    name = fields.Char(required=True)
    module_name = fields.Char(
        string="Technical name",
        required=True,
        help="Name of the module the project makes: lower case letters, "
        "digits and underscores. The external ids of its views in the "
        "database start with it.",
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("applied", "Applied"),
        ],
        default="draft",
        required=True,
        readonly=True,
        copy=False,
    )
    user_id = fields.Many2one(
        "res.users",
        string="Editor",
        default=lambda self: self.env.user,
        help="The only user who sees the draft in the views.",
    )
    change_ids = fields.One2many(
        "erplibre.studio.change", "project_id", string="Changes", copy=False
    )
    change_count = fields.Integer(compute="_compute_change_count")
    field_ids = fields.Many2many(
        "ir.model.fields",
        "erplibre_studio_project_field_rel",
        "project_id",
        "field_id",
        string="Fields created",
        readonly=True,
        copy=False,
    )
    studio_view_ids = fields.Many2many(
        "ir.ui.view",
        "erplibre_studio_project_view_rel",
        "project_id",
        "view_id",
        string="Views created",
        readonly=True,
        copy=False,
    )
    draft_revision = fields.Integer(readonly=True, copy=False)
    applied_snapshot = fields.Text(readonly=True, copy=False)
    applied_date = fields.Datetime(readonly=True, copy=False)
    module_id = fields.Many2one(
        "ir.module.module", compute="_compute_module_id", string="Module"
    )
    module_state = fields.Selection(
        STATES, compute="_compute_module_id", string="Module state"
    )

    _sql_constraints = [
        (
            "module_name_uniq",
            "unique(module_name)",
            "Another studio project generates this module.",
        ),
    ]

    # ── fields ──────────────────────────────────────────────────────────

    @api.depends("change_ids")
    def _compute_change_count(self):
        for project in self:
            project.change_count = len(project.change_ids)

    @api.depends("module_name")
    def _compute_module_id(self):
        Module = self.env["ir.module.module"].sudo()
        for project in self:
            module = Module.search([("name", "=", project.module_name or "")], limit=1)
            project.module_id = module
            project.module_state = module.state or False

    # ── constraints ─────────────────────────────────────────────────────

    @api.constrains("module_name")
    def _check_module_name(self):
        for project in self:
            name = project.module_name
            if not studio_arch.valid_module_name(name):
                raise ValidationError(
                    self.env._(
                        "%(name)s is not a valid technical name: lower case "
                        "letters, digits and underscores, starting with a letter.",
                        name=name,
                    )
                )
            path = get_module_path(name, display_warning=False)
            own = bool(path) and project._is_own_directory(path)
            if path and not own:
                raise ValidationError(
                    self.env._(
                        "A module named %(name)s already exists in %(path)s.",
                        name=name,
                        path=path,
                    )
                )
            module = self.env["ir.module.module"].sudo().search([("name", "=", name)])
            if module and not own:
                raise ValidationError(
                    self.env._("A module named %(name)s is already known.", name=name)
                )

    def _is_own_directory(self, path):
        """Whether the module directory ``path`` was made from this
        project, so that its name does not collide with it. Without a
        generation, no directory is: erplibre_studio_generate recognises
        the ones it writes."""
        self.ensure_one()
        return False

    @api.model
    def _managed_fields(self):
        """The names of the fields of a project only its own methods
        write."""
        return MANAGED_FIELDS

    def _check_managed_fields(self, vals_list):
        """Refuse a write of ``_managed_fields`` that does not come from
        the project itself."""
        if self.env.su and self.env.context.get(INTERNAL_KEY):
            return
        names = sorted({n for vals in vals_list for n in vals} & self._managed_fields())
        if names:
            raise UserError(
                self.env._(
                    "These fields of a studio project are managed by the "
                    "studio: %(fields)s",
                    fields=", ".join(names),
                )
            )

    def _internal(self):
        """The project as its own methods write it: see INTERNAL_KEY."""
        return self.sudo().with_context(**{INTERNAL_KEY: True})

    @api.model_create_multi
    def create(self, vals_list):
        self._check_managed_fields(vals_list)
        return super().create(vals_list)

    def write(self, vals):
        self._check_managed_fields([vals])
        if "module_name" in vals:
            for project in self:
                if project.module_name != vals["module_name"]:
                    project._rename_studio_xmlids(vals["module_name"])
        editors = {project: project.user_id for project in self}
        res = super().write(vals)
        for project, editor in editors.items():
            if project.user_id != editor:
                # The draft moves to another user: a new preview revision,
                # so that no view cached for the former editor is reused.
                project._internal().draft_revision += 1
        return res

    def unlink(self):
        for project in self:
            if project.studio_view_ids or project.field_ids:
                raise UserError(
                    self.env._(
                        "Revert the project %(name)s before deleting it: its "
                        "fields and views are in the database.",
                        name=project.name,
                    )
                )
        return super().unlink()

    # ── guards ──────────────────────────────────────────────────────────

    @api.model
    def _check_studio_access(self):
        """Settings group and developer mode, as the developer panel."""
        self.env["erplibre.developer"]._check_panel_access()

    # ── state ───────────────────────────────────────────────────────────

    def _current_snapshot(self):
        self.ensure_one()
        return json.dumps(self.change_ids._snapshot(), sort_keys=True)

    def _touch(self):
        """After a change of the draft: new preview revision, new state."""
        for project in self:
            project._internal().draft_revision += 1
            project._update_state()

    def _update_state(self):
        for project in self:
            current = project._current_snapshot()
            if project.applied_snapshot and current == project.applied_snapshot:
                state = project._applied_state(current)
            else:
                state = "draft"
            if project.state != state:
                project._internal().state = state

    def _applied_state(self, snapshot):
        """The state of the project when ``snapshot``, the JSON of its
        changes, is the one applied to the database."""
        self.ensure_one()
        return "applied"

    def _editing(self):
        """The project as its editor operations change its changes: they
        touch the draft once, at the end."""
        return self.with_context(**{NO_TOUCH_KEY: True})

    # ── draft ───────────────────────────────────────────────────────────

    def _view_changes(self, view):
        self.ensure_one()
        return self.change_ids.filtered(lambda c: c.view_id == view).sorted(
            lambda c: (c.sequence, c.id)
        )

    def _base_arch(self, view, branding=False):
        """The combined arch of ``view`` without the views of the project."""
        self.ensure_one()
        context = {EXCLUDE_KEY: ViewExclusion(self.studio_view_ids.ids)}
        if branding:
            context["inherit_branding"] = True
        View = self.env["ir.ui.view"].sudo().with_context(**context)
        return View.browse(view.id)._get_combined_arch()

    def _draft_arch(self, view):
        """(arch, errors): the base arch of ``view`` with the changes of the
        project applied; ``errors`` maps a change id to why it does not
        apply."""
        self.ensure_one()
        return self._draft_arch_without(view, self.env["erplibre.studio.change"])

    def _draft_arch_without(self, view, skipped):
        """``_draft_arch`` of ``view`` with the changes ``skipped`` left
        out."""
        self.ensure_one()
        changes = [c._as_dict() for c in self._view_changes(view) if c not in skipped]
        return studio_arch.apply_changes(
            self._base_arch(view), changes, view.type, self._arch_message
        )

    @api.model
    def _preview_project(self):
        """The project whose draft get_views shows: the one named by the
        context, when the user is its editor."""
        value = self.env.context.get(PREVIEW_KEY)
        if not value:
            return self.browse()
        try:
            project_id = int(str(value).split(":", 1)[0])
        except ValueError:
            return self.browse()
        project = self.sudo().browse(project_id).exists()
        if (
            not project
            or project.user_id != self.env.user
            or not self.env.user.has_group("base.group_system")
        ):
            return self.browse()
        return project

    def _preview_arch(self, arch, view, model):
        """``arch`` (the combined arch of ``view``, without the project
        views) with the draft applied. A new field not yet in the database
        shows as a placeholder in a form and is left out of the other view
        types."""
        self.ensure_one()
        changes = [c._as_dict() for c in self._view_changes(view)]
        if not changes:
            return arch
        arch, _errors = studio_arch.apply_changes(
            arch, changes, view.type, self._arch_message
        )
        Model = self.env[model]
        pending = {
            c.field_name: c._payload().get("field") or {}
            for c in self.change_ids
            if c.change_type == "add_field" and c.model == model
        }
        for node in list(arch.iter("field")):
            name = node.get("name")
            if name not in pending or name in Model._fields:
                continue
            parent = node.getparent()
            if view.type != "form":
                remove_keeping_tail(node)
                continue
            placeholder = etree_placeholder(
                pending[name].get("field_description") or name,
                self.env._("new field, created by Apply"),
            )
            placeholder.tail = node.tail
            parent.replace(node, placeholder)
        return arch

    # ── operations of the editor ────────────────────────────────────────

    def _next_sequence(self):
        return max(self.change_ids.mapped("sequence") or [0]) + 10

    def _project_field_changes(self, model=None):
        return self.change_ids.filtered(
            lambda c: c.change_type == "add_field" and (not model or c.model == model)
        )

    def _taken_field_names(self, model):
        names = set(self.env[model]._fields)
        names |= set(
            self.env["erplibre.studio.change"]
            .search([("model", "=", model), ("change_type", "=", "add_field")])
            .mapped("field_name")
        )
        return names

    def _clean_field_definition(self, model, field, name=None):
        """A checked definition of a new field: {ttype, field_description,
        readonly, help, selection, relation, currency_field}. ``name`` is
        the field name; None makes one from the label."""
        ttype = field.get("ttype")
        if ttype not in NEW_FIELD_TYPES:
            raise UserError(self.env._("Unknown field type %(type)s.", type=ttype))
        label = (field.get("field_description") or "").strip()
        label = label or self.env._("New field")
        help_text = (field.get("help") or "").strip()
        self._check_field_texts(label, help_text)
        name = self._clean_field_name(model, label, field, name)
        # « Required » stays on the view node: on the model it would set
        # NOT NULL on a table that has rows.
        definition = {
            "ttype": ttype,
            "field_description": label,
            "readonly": bool(field.get("readonly")),
            "help": help_text,
        }
        if ttype == "selection":
            definition["selection"] = self._clean_selection(field)
        elif ttype == "many2one":
            definition["relation"] = self._clean_relation(field)
        elif ttype == "monetary":
            definition["currency_field"] = self._clean_currency(model, field)
        return name, definition

    @api.model
    def _check_field_texts(self, label, help_text):
        """Raise UserError when the label or the tooltip of a new field
        cannot be recorded. Every text is accepted here; a module that
        copies them elsewhere narrows the check."""

    def _clean_field_name(self, model, label, field, name):
        if name is None:
            taken = self._taken_field_names(model)
            name = field.get("name") or studio_arch.field_name_from_label(label, taken)
            if name in taken:
                raise UserError(
                    self.env._("The field %(name)s already exists.", name=name)
                )
        if not studio_arch.valid_field_name(name):
            raise UserError(
                self.env._(
                    "%(name)s is not a valid field name: x_ then lower case "
                    "letters, digits and underscores.",
                    name=name,
                )
            )
        return name

    def _clean_selection(self, field):
        """[[value, label]]: non-empty values, each once."""
        selection = []
        for item in field.get("selection") or []:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                continue
            value, text = (str(item[0]).strip(), str(item[1]).strip())
            if value and value not in [s[0] for s in selection]:
                selection.append([value, text or value])
        return selection or [["value_1", self.env._("Value 1")]]

    def _clean_relation(self, field):
        relation = field.get("relation") or "res.partner"
        Comodel = self.env.get(relation)
        if Comodel is None or Comodel._transient or Comodel._abstract:
            raise UserError(
                self.env._("%(model)s cannot be the comodel.", model=relation)
            )
        return relation

    def _clean_currency(self, model, field):
        """The many2one to res.currency of a monetary field: the one given,
        else the ``currency_id`` of the model."""
        Model = self.env[model]
        currency = field.get("currency_field") or next(
            (n for n in ("currency_id", "x_currency_id") if n in Model._fields),
            "",
        )
        target = Model._fields.get(currency)
        if not (
            target
            and target.type == "many2one"
            and target.comodel_name == "res.currency"
        ):
            raise UserError(
                self.env._(
                    "A monetary field needs a many2one to res.currency on "
                    "%(model)s.",
                    model=model,
                )
            )
        return currency

    def _refuse(self, refusal):
        """Raise the UserError of ``refusal``, an ArchError or None."""
        if refusal is not None:
            raise UserError(self._arch_message(refusal))

    def _check_drop(self, arch, op, view_type):
        target = op.get("target")
        position = op.get("position") or "after"
        node = self._locate(arch, target)
        self._refuse(studio_arch.drop_refusal(view_type, node, position))
        return target, position, node

    def _locate(self, arch, xpath):
        try:
            return studio_arch.locate(arch, xpath or "")
        except studio_arch.ArchError as exc:
            raise UserError(self._arch_message(exc)) from exc

    @api.model
    def _arch_message(self, exc):
        """The message of ``exc`` in the user's language: an ``ArchError``
        by its code, any other exception as it reads."""
        code = getattr(exc, "code", None)
        params = getattr(exc, "params", {})
        messages = {
            "no_node": lambda: self.env._("No node at %(xpath)s.", **params),
            "invalid_xpath": lambda: self.env._(
                "Invalid XPath %(xpath)s: %(error)s", **params
            ),
            "unknown_change": lambda: self.env._(
                "Unknown change type %(type)s.", **params
            ),
            "unknown_position": lambda: self.env._(
                "Unknown position %(position)s.", **params
            ),
            "no_drop_inside": lambda: self.env._(
                "Nothing can be dropped inside <%(tag)s>.", **params
            ),
            "no_drop": lambda: self.env._("Nothing can be dropped there."),
            "chain": lambda: self.env._(
                "Nothing can be dropped between the nodes of a t-if chain."
            ),
            "no_move": lambda: self.env._("<%(tag)s> cannot move.", **params),
            "chain_move": lambda: self.env._("A node of a t-if chain cannot move."),
            "outside_template": lambda: self.env._(
                "This field is loaded by the view for its templates: it "
                "cannot move nor be hidden."
            ),
            "no_hide_root": lambda: self.env._("The view itself cannot be hidden."),
            "no_hide": lambda: self.env._("<%(tag)s> cannot be hidden.", **params),
            "chain_hide": lambda: self.env._(
                "The t-if or the t-elif of a chain cannot be hidden."
            ),
            "content_directive": lambda: self.env._(
                "<%(tag)s> replaces its content: nothing dropped into it shows.",
                **params,
            ),
            "template_move": lambda: self.env._(
                "A node of a template cannot move out of the templates."
            ),
            "unsafe_attribute": lambda: self.env._(
                "A change cannot write the attribute %(attribute)s.", **params
            ),
            "unknown_node": lambda: self.env._(
                "A change cannot add <%(tag)s>.", **params
            ),
            "bad_operator": lambda: self.env._(
                "The operator %(operator)s does not apply to a %(type)s field.",
                **params,
            ),
            "bad_color": lambda: self.env._("Invalid color %(color)s.", **params),
            "bad_color_operator": lambda: self.env._(
                "Invalid operator %(operator)s.", **params
            ),
            "bad_color_value": lambda: self.env._(
                "The value %(value)s cannot be used in a timeline color: it "
                "holds « : » or « ; ».",
                **params,
            ),
            "bad_field": lambda: self.env._("Invalid field %(field)s.", **params),
            "bad_order": lambda: self.env._("Invalid order %(order)s.", **params),
        }
        if code in messages:
            return messages[code]()
        return str(exc)

    def _add_change(self, view, change_type, xpath, position, payload):
        Change = self.env["erplibre.studio.change"].with_context(**{NO_TOUCH_KEY: True})
        return Change.create(
            {
                "project_id": self.id,
                "sequence": self._next_sequence(),
                "change_type": change_type,
                "model": view.model,
                "view_id": view.id,
                "view_type": view.type,
                "xpath": xpath,
                "position": position,
                "payload": json.dumps(payload, sort_keys=True),
            }
        )

    def _field_add_change(self, model, name):
        return self._project_field_changes(model).filtered(
            lambda c: c.field_name == name
        )[:1]

    @api.model
    def _view_types(self):
        """The view types the studio edits in this database: those of
        ``VIEW_TYPES`` that ir.ui.view knows. « timeline » is one only when
        a module (web_timeline) adds it."""
        known = self.env["ir.ui.view"]._fields["type"].get_values(self.env)
        return tuple(t for t in studio_arch.VIEW_TYPES if t in known)

    def _apply_operation(self, view, op):
        """Record the editor operation ``op`` (a dict with a ``type``) on
        ``view`` as a change, or update the change it refines. Return the
        change touched, or an empty recordset. Raise UserError when the
        operation does not fit the draft arch."""
        self.ensure_one()
        self = self._editing()
        if view.type not in self._view_types():
            raise UserError(
                self.env._("The studio does not edit %(type)s views.", type=view.type)
            )
        otype = op.get("type")
        handlers = {
            "add_field": self._op_add_field,
            "add_existing_field": self._op_add_existing_field,
            "add_filter": self._op_add_filter,
            "add_group_by": self._op_add_group_by,
            "add_separator": self._op_add_separator,
            "add_widget": self._op_add_widget,
            "move": self._op_move,
            "update_field": lambda view, arch, op: self._update_field(view, op),
            "remove": self._remove_node,
            "hide": self._op_hide,
            "set_attribute": self._op_set_attribute,
        }
        for name in studio_arch.ATTRIBUTE_CHANGES:
            handlers[name] = self._attribute_operation
        if otype not in handlers:
            raise UserError(self.env._("Unknown operation %(type)s.", type=otype))
        if otype not in studio_arch.VIEW_OPERATIONS[view.type]:
            raise UserError(
                self.env._(
                    "The operation %(type)s does not apply to a %(view_type)s view.",
                    type=otype,
                    view_type=view.type,
                )
            )
        arch, _errors = self._draft_arch(view)
        change = handlers[otype](view, arch, op)
        self._touch()
        if change.exists():
            _arch, errors = self._draft_arch(view)
            if change.id in errors:
                raise UserError(errors[change.id])
        return change.exists()

    # ── fields named by an operation ────────────────────────────────────

    @api.model
    def _field_info(self, model, name):
        """The ``fields_get`` description of the field ``name`` of
        ``model``; UserError when the model has no such field."""
        Model = self.env[model]
        if not name or name not in Model._fields:
            raise UserError(self.env._("Unknown field %(name)s.", name=name))
        return Model.fields_get([name], attributes=FIELD_INFO)[name]

    def _check_groupable(self, model, name):
        info = self._field_info(model, name)
        if not info.get("groupable"):
            raise UserError(
                self.env._("The records cannot be grouped by %(name)s.", name=name)
            )
        return info

    def _check_interval(self, info, interval):
        """``interval`` checked against the field ``info``; None for none."""
        if not interval:
            return None
        if interval not in studio_arch.INTERVALS:
            raise UserError(
                self.env._("Unknown interval %(interval)s.", interval=interval)
            )
        if info["type"] not in studio_arch.DATE_TYPES:
            raise UserError(self.env._("Only a date field takes an interval."))
        return interval

    def _check_pivot_axis(self, model, name, axis, interval=None):
        """The pivot attributes {type, interval} of the field ``name`` on
        ``axis``: a measure adds up a number, a row or a column groups."""
        if axis not in studio_arch.PIVOT_AXES:
            raise UserError(
                self.env._(
                    "Choose the axis of the field: row, column or measure.",
                )
            )
        info = self._field_info(model, name)
        if axis == "measure":
            if info["type"] not in studio_arch.NUMBER_TYPES or not info.get(
                "aggregator"
            ):
                raise UserError(
                    self.env._(
                        "%(name)s cannot be a measure: a measure adds up a "
                        "number field.",
                        name=name,
                    )
                )
            if interval:
                raise UserError(self.env._("A measure takes no interval."))
            return {"type": axis}
        self._check_groupable(model, name)
        attrs = {"type": axis}
        interval = self._check_interval(info, interval)
        if interval:
            attrs["interval"] = interval
        return attrs

    def _typed_value(self, info, value):
        """``value``, typed as the field ``info`` stores it, for a search
        filter or a timeline color rule."""
        ttype = info["type"]
        try:
            if ttype == "boolean":
                if isinstance(value, str):
                    return value.strip().lower() in ("1", "true", "yes")
                return bool(value)
            if ttype == "integer":
                return int(value)
            if ttype in ("float", "monetary"):
                return float(value)
            if ttype == "date":
                return fields.Date.to_string(fields.Date.to_date(value))
            if ttype == "datetime":
                return fields.Datetime.to_string(fields.Datetime.to_datetime(value))
            if ttype == "selection":
                if value not in [item[0] for item in info.get("selection") or []]:
                    raise ValueError(value)
                return value
            text = str(value if value is not None else "").strip()
            if not text:
                raise ValueError(value)
            return text
        except (TypeError, ValueError):
            raise UserError(
                self.env._(
                    "%(value)s is not a value of the field %(name)s.",
                    value=value,
                    name=info.get("string"),
                )
            ) from None

    def _check_domain(self, model, terms):
        """Raise UserError when the domain of ``terms`` does not search
        ``model``."""
        try:
            with self.env.cr.savepoint():
                self.env[model].sudo()._search([tuple(term) for term in terms])
        except (ValueError, KeyError, TypeError) as exc:
            raise UserError(
                self.env._("The filter does not apply: %(error)s", error=exc)
            ) from exc

    @api.model
    def _clean_widget(self, name):
        if not name or not re.match(r"^[a-z][a-z0-9_]*$", name):
            raise UserError(self.env._("Invalid widget %(name)s.", name=name))
        return name

    # ── operations of the editor, by type ───────────────────────────────

    def _op_add_field(self, view, arch, op):
        target, position, _node = self._check_drop(arch, op, view.type)
        name, definition = self._clean_field_definition(
            view.model, op.get("field") or {}
        )
        return self._add_change(
            view,
            "add_field",
            target,
            position,
            {"field_name": name, "field": definition, "node_attrs": {}},
        )

    def _field_scope(self, arch, node, view_type):
        """The names of the fields a new field must not repeat: those of the
        template the drop lands in, or of the view outside the templates;
        the whole arch for the other view types."""
        if view_type not in studio_arch.TEMPLATED_TYPES:
            return studio_arch.arch_field_names(arch)
        for item in [node, *node.iterancestors()]:
            if studio_arch.is_template(item):
                return studio_arch.template_field_names(view_type, item)
        return self._loaded_fields(arch)

    @api.model
    def _loaded_fields(self, arch):
        """The names of the fields a QWeb view loads outside its templates."""
        return {
            child.get("name")
            for child in studio_arch.elements(arch)
            if child.tag == "field"
        }

    def _op_add_existing_field(self, view, arch, op):
        target, position, node = self._check_drop(arch, op, view.type)
        name = op.get("field_name")
        if name not in self.env[view.model]._fields:
            raise UserError(self.env._("Unknown field %(name)s.", name=name))
        if name in self._field_scope(arch, node, view.type):
            raise UserError(
                self.env._("The field %(name)s is already in the view.", name=name)
            )
        node_attrs = {}
        extra = {}
        if view.type == "timeline" and studio_arch.in_template(node):
            extra = self._item_field(view.model, arch, name)
        elif view.type == "search":
            if not self._field_info(view.model, name).get("searchable"):
                raise UserError(
                    self.env._("The records cannot be searched by %(name)s.", name=name)
                )
        elif view.type == "pivot":
            node_attrs = self._check_pivot_axis(
                view.model, name, op.get("axis"), op.get("interval")
            )
        elif view.type == "kanban" and op.get("widget"):
            node_attrs["widget"] = self._clean_widget(op["widget"])
        return self._add_change(
            view,
            "add_existing_field",
            target,
            position,
            {"field_name": name, "node_attrs": node_attrs, **extra},
        )

    def _item_field(self, model, arch, name):
        """The payload keys of a field dropped into a timeline item: how it
        shows (``item``, see ``arch.item_value``), and ``load`` when the
        view does not load it yet."""
        info = self._field_info(model, name)
        if info["type"] not in studio_arch.ITEM_FIELD_TYPES:
            raise UserError(
                self.env._(
                    "A timeline item cannot show %(name)s: its type is %(type)s.",
                    name=info.get("string") or name,
                    type=info["type"],
                )
            )
        return {
            "item": studio_arch.item_kind(info["type"]),
            "load": name not in self._loaded_fields(arch),
        }

    def _op_add_filter(self, view, arch, op):
        """A <filter> with a domain built from conditions {field, operator,
        value}, joined by AND."""
        target, position, _node = self._check_drop(arch, op, view.type)
        conditions = op.get("conditions")
        if conditions is None and op.get("field"):
            conditions = [
                {
                    "field": op.get("field"),
                    "operator": op.get("operator"),
                    "value": op.get("value"),
                }
            ]
        if not conditions or not isinstance(conditions, list):
            raise UserError(self.env._("A filter needs at least one condition."))
        terms, cleaned, names, labels = [], [], [], []
        for condition in conditions:
            name = (condition or {}).get("field")
            info = self._field_info(view.model, name)
            if not info.get("searchable"):
                raise UserError(
                    self.env._("The records cannot be searched by %(name)s.", name=name)
                )
            operator = condition.get("operator") or "="
            value = condition.get("value")
            if operator in ("set", "not set"):
                value = None
            else:
                value = self._typed_value(info, value)
            try:
                terms.append(
                    studio_arch.filter_condition(name, info["type"], operator, value)
                )
            except studio_arch.ArchError as exc:
                raise UserError(self._arch_message(exc)) from exc
            cleaned.append({"field": name, "operator": operator, "value": value})
            names.append(name)
            labels.append(info.get("string") or name)
        self._check_domain(view.model, terms)
        label = (op.get("label") or "").strip() or ", ".join(labels)
        node_name = studio_arch.node_name_from_label(
            "studio_filter", label, studio_arch.arch_names(arch)
        )
        attrs = {
            "name": node_name,
            "string": label,
            "domain": studio_arch.domain_text(terms),
        }
        return self._add_change(
            view,
            "add_node",
            target,
            position,
            {
                "kind": "filter",
                "node_name": node_name,
                "node": {"tag": "filter", "attrs": attrs},
                "conditions": cleaned,
                "fields": sorted(set(names)),
            },
        )

    def _op_add_group_by(self, view, arch, op):
        """A <filter> that groups by a field, by ``interval`` for a date."""
        target, position, _node = self._check_drop(arch, op, view.type)
        name = op.get("field_name")
        info = self._check_groupable(view.model, name)
        interval = self._check_interval(info, op.get("interval"))
        group_by = f"{name}:{interval}" if interval else name
        if any(
            studio_arch.group_by_of(node) == group_by for node in arch.iter("filter")
        ):
            raise UserError(
                self.env._(
                    "The search view already groups by %(group_by)s.",
                    group_by=group_by,
                )
            )
        label = (op.get("label") or "").strip() or info.get("string") or name
        node_name = studio_arch.node_name_from_label(
            "studio_group_by",
            f"{name} {interval or ''}",
            studio_arch.arch_names(arch),
        )
        attrs = {
            "name": node_name,
            "string": label,
            "context": studio_arch.group_by_context(name, interval),
        }
        return self._add_change(
            view,
            "add_node",
            target,
            position,
            {
                "kind": "group_by",
                "node_name": node_name,
                "node": {"tag": "filter", "attrs": attrs},
                "group_by": group_by,
                "fields": [name],
            },
        )

    def _op_add_separator(self, view, arch, op):
        target, position, _node = self._check_drop(arch, op, view.type)
        return self._add_change(
            view,
            "add_node",
            target,
            position,
            {"kind": "separator", "node": {"tag": "separator", "attrs": {}}},
        )

    def _op_add_widget(self, view, arch, op):
        """A <widget> of ``WIDGETS`` in a template of the view."""
        target, position, _node = self._check_drop(arch, op, view.type)
        widget = op.get("widget")
        if widget not in studio_arch.WIDGETS:
            raise UserError(self.env._("Invalid widget %(name)s.", name=widget))
        attrs = {"name": widget}
        given = op.get("attrs") or {}
        for key in studio_arch.WIDGETS[widget]:
            value = str(given.get(key) or "").strip()
            if value:
                attrs[key] = value
        if not re.match(r"^[a-z0-9 _-]*$", attrs.get("bg_color", "")):
            raise UserError(
                self.env._("Invalid color %(color)s.", color=attrs["bg_color"])
            )
        return self._add_change(
            view,
            "add_node",
            target,
            position,
            {"kind": "widget", "node": {"tag": "widget", "attrs": attrs}},
        )

    def _op_move(self, view, arch, op):
        """Move a node; in a pivot, ``axis`` also moves a field to another
        axis."""
        target, position, node = self._check_drop(arch, op, view.type)
        source_path = op.get("source")
        source = self._locate(arch, source_path)
        self._refuse(studio_arch.move_refusal(view.type, source))
        if source is node or source in node.iterancestors():
            raise UserError(self.env._("A node cannot move into itself."))
        destination = node if position == "inside" else node.getparent()
        if (
            view.type in studio_arch.TEMPLATED_TYPES
            and studio_arch.in_template(source)
            and not studio_arch.in_template(destination)
        ):
            self._refuse(
                studio_arch.ArchError(
                    "A node of a template cannot move out of the templates.",
                    "template_move",
                )
            )
        payload = {"source": source_path}
        field_name = studio_arch.shown_field_name(view.type, source)
        if field_name:
            payload["field_name"] = field_name
        elif source.get("name"):
            payload["node_name"] = source.get("name")
        axis = op.get("axis")
        if view.type == "pivot" and source.tag == "field" and axis:
            if axis != source.get("type"):
                interval = None if axis == "measure" else source.get("interval")
                attrs = self._check_pivot_axis(
                    view.model, source.get("name"), axis, interval
                )
                if axis == "measure" and source.get("interval"):
                    attrs["interval"] = ""
                payload["attrs"] = attrs
        if payload.get("attrs"):
            move = {
                "type": "move",
                "xpath": target,
                "position": position,
                "payload": payload,
            }
            try:
                payload["attrs_xpath"] = studio_arch.moved_node_xpath(
                    arch, move, view.type
                )
            except Exception as exc:  # noqa: BLE001 - reported as the move error
                raise UserError(self._arch_message(exc)) from exc
        return self._add_change(view, "move", target, position, payload)

    def _op_hide(self, view, arch, op):
        """Hide a node: by its hide attribute, or, in a search or a pivot
        view, by removing it (see ``HIDE_MODES``)."""
        if studio_arch.hide_mode(view.type) == "remove":
            if not op.get("value"):
                raise UserError(
                    self.env._(
                        "A removed node comes back with Undo, or by deleting "
                        "the change that removed it."
                    )
                )
            return self._remove_node(view, arch, op)
        node = self._locate(arch, op.get("target"))
        self._refuse(studio_arch.hide_refusal(view.type, node))
        return self._attribute_operation(view, arch, op)

    def _added_changes(self, view, xpath):
        """The change of ``view`` that added the node at ``xpath`` of the
        draft, or an empty recordset for a node of the view itself. The
        node is found by the change that inserts it, whatever its name: a
        ribbon is named after its widget, a separator has no name."""
        changes = self._view_changes(view)
        key = studio_arch.added_key(
            self._base_arch(view), [c._as_dict() for c in changes], view.type, xpath
        )
        return changes.filtered(lambda c: str(c.id) == key)

    def _replaced_change(self, view, arch, existing, xpath):
        """The change among ``existing`` that a new value for the node at
        ``xpath`` replaces: by name or at the root, the latest one; by
        position, only the last change of the view, since a later change
        may have moved what the position names."""
        replaced = existing[-1:]
        stable = xpath.startswith("//") or xpath == f"/{arch.tag}"
        if replaced and not stable and replaced != self._view_changes(view)[-1:]:
            replaced = existing.browse()
        return replaced

    def _attribute_operation(self, view, arch, op):
        otype = op["type"]
        xpath = op.get("target")
        node = self._locate(arch, xpath)
        value = op.get("value")
        if otype in studio_arch.BOOLEAN_CHANGES:
            value = bool(value)
        elif otype == "optional":
            value = value or ""
            if value not in studio_arch.OPTIONAL_VALUES or view.type != "list":
                raise UserError(self.env._("Only a list column can be optional."))
        else:
            value = (value or "").strip()
        name = node.get("name") if node.tag == "field" else None
        own = name and self._field_add_change(view.model, name)
        field_attr = {
            "relabel": "field_description",
            "readonly": "readonly",
            "help": "help",
        }.get(otype)
        if own and field_attr:
            # A field of the project: the change goes to its definition.
            return self._update_field(
                view, {"field_name": name, "field": {field_attr: value}}
            )
        if otype == "relabel" and value and node.tag != "field":
            added = self._added_changes(view, xpath)
            if added.change_type == "add_node":
                # An element of the project: the label goes to its definition.
                payload = added._payload()
                payload["node"]["attrs"]["string"] = value
                added._set_payload(payload)
                return added
        existing = self._view_changes(view).filtered(
            lambda c: c.change_type == otype and c.xpath == xpath
        )
        replaced = self._replaced_change(view, arch, existing, xpath)
        if otype in studio_arch.BOOLEAN_CHANGES:
            if replaced:
                before, _errors = self._draft_arch_without(view, replaced)
                original = self._locate(before, xpath)
            else:
                original = node
            attribute = (
                studio_arch.hide_attribute(view.type)
                if otype == "hide"
                else studio_arch.ATTRIBUTE_CHANGES[otype]
            )
            if value == studio_arch.constant_true(original.get(attribute)):
                # The node is back to the arch without the change: a
                # condition of the view (« invisible="is_company" ») stays.
                replaced.unlink()
                return replaced.browse()
        if replaced:
            payload = replaced._payload()
            payload["value"] = value
            replaced._set_payload(payload)
            return replaced
        return self._add_change(view, otype, xpath, "attributes", {"value": value})

    def _attribute_value(self, view, node, kind, value):
        """(text, fields): the attribute text of ``value`` for an attribute
        of ``kind`` (see ``SETTABLE_ATTRIBUTES``), and the fields it names.
        An empty text removes the attribute."""
        if kind == "bool":
            if value in (None, ""):
                return "", []
            if isinstance(value, str):
                value = studio_arch.constant_true(value)
            return ("True" if value else "False"), []
        if kind == "colors":
            return self._colors_value(view.model, value)
        if value in (None, "", False):
            return "", []
        if not isinstance(value, str):
            raise UserError(self.env._("Invalid value %(value)s.", value=value))
        check = {
            "group_field": self._group_field_value,
            "relation_group_field": self._relation_group_field_value,
            "date_field": self._typed_field_value,
            "number_field": self._typed_field_value,
            "order": self._order_value,
            "axis": self._axis_value,
            "interval": self._interval_value,
            "widget": lambda model, node, kind, value: (self._clean_widget(value), []),
            "timeline_mode": self._mode_value,
        }.get(kind)
        if not check:
            raise UserError(self.env._("Invalid value %(value)s.", value=value))
        return check(view.model, node, kind, value.strip())

    def _group_field_value(self, model, node, kind, value):
        self._check_groupable(model, value)
        return value, [value]

    def _relation_group_field_value(self, model, node, kind, value):
        info = self._check_groupable(model, value)
        if info["type"] not in studio_arch.RELATION_TYPES:
            raise UserError(
                self.env._(
                    "A timeline groups its items by a many2one or a many2many "
                    "field only, not by %(name)s.",
                    name=value,
                )
            )
        return value, [value]

    def _typed_field_value(self, model, node, kind, value):
        info = self._field_info(model, value)
        types = studio_arch.DATE_TYPES if kind == "date_field" else ("integer", "float")
        if info["type"] not in types or not info.get("store"):
            raise UserError(
                self.env._(
                    "%(name)s does not fit this attribute: a stored %(types)s "
                    "field is needed.",
                    name=value,
                    types=" / ".join(types),
                )
            )
        return value, [value]

    def _order_value(self, model, node, kind, value):
        try:
            names = studio_arch.order_fields(value)
        except studio_arch.ArchError as exc:
            raise UserError(self._arch_message(exc)) from exc
        for name in names:
            if not self._field_info(model, name).get("sortable"):
                raise UserError(
                    self.env._("The records cannot be sorted by %(name)s.", name=name)
                )
        return value, sorted(set(names))

    def _axis_value(self, model, node, kind, value):
        interval = node.get("interval")
        if value == "measure" and interval:
            raise UserError(
                self.env._("A measure takes no interval: remove the interval first.")
            )
        self._check_pivot_axis(model, node.get("name"), value, interval)
        return value, []

    def _interval_value(self, model, node, kind, value):
        if node.get("type") == "measure":
            raise UserError(self.env._("A measure takes no interval."))
        info = self._field_info(model, node.get("name"))
        return self._check_interval(info, value), []

    def _mode_value(self, model, node, kind, value):
        if value not in studio_arch.TIMELINE_MODES:
            raise UserError(self.env._("Invalid value %(value)s.", value=value))
        return value, []

    def _colors_value(self, model, rules):
        """The ``colors`` text of a timeline from rules {color, field,
        operator, value}."""
        if rules in (None, "", False, []):
            return "", []
        if not isinstance(rules, list):
            raise UserError(self.env._("Invalid value %(value)s.", value=rules))
        typed = []
        for rule in rules:
            rule = dict(rule or {})
            info = self._field_info(model, rule.get("field"))
            if info["type"] not in studio_arch.COLOR_FIELD_TYPES:
                raise UserError(
                    self.env._(
                        "A color rule cannot compare %(name)s, a %(type)s field.",
                        name=info.get("string") or rule.get("field"),
                        type=info["type"],
                    )
                )
            rule["value"] = self._typed_value(info, rule.get("value"))
            typed.append(rule)
        try:
            text = studio_arch.colors_text(typed)
        except studio_arch.ArchError as exc:
            raise UserError(self._arch_message(exc)) from exc
        return text, sorted({rule["field"] for rule in typed})

    @api.model
    def _normal_attribute(self, kind, text):
        """``text``, the attribute of a node, as ``_attribute_value`` would
        write it, to tell whether a value brings the node back."""
        if text is None:
            return ""
        if kind == "bool":
            if studio_arch.constant_true(text):
                return "True"
            if text in ("0", "False", "false"):
                return "False"
        return text

    def _op_set_attribute(self, view, arch, op):
        """Set an attribute of ``SETTABLE_ATTRIBUTES`` on a node. A value
        that brings the node back to the arch without the change removes
        the change."""
        xpath = op.get("target")
        node = self._locate(arch, xpath)
        attribute = op.get("attribute")
        settable = studio_arch.SETTABLE_ATTRIBUTES.get(view.type, {})
        kind = settable.get(node.tag, {}).get(attribute)
        if node.tag == view.type and node.getparent() is not None:
            kind = None
        if not kind:
            raise UserError(
                self.env._(
                    "The attribute %(attribute)s of <%(tag)s> cannot be set here.",
                    attribute=attribute,
                    tag=node.tag,
                )
            )
        value, named = self._attribute_value(view, node, kind, op.get("value"))
        required = studio_arch.REQUIRED_ATTRIBUTES.get((view.type, node.tag), ())
        if not value and attribute in required:
            raise UserError(
                self.env._(
                    "The view needs the attribute %(attribute)s.", attribute=attribute
                )
            )
        existing = self._view_changes(view).filtered(
            lambda c: c.change_type == "set_attribute"
            and c.xpath == xpath
            and c._payload().get("attribute") == attribute
        )
        replaced = self._replaced_change(view, arch, existing, xpath)
        if replaced:
            before, _errors = self._draft_arch_without(view, replaced)
            original = self._locate(before, xpath).get(attribute)
        else:
            original = node.get(attribute)
        if value == self._normal_attribute(kind, original):
            replaced.unlink()
            return replaced.browse()
        payload = {"attribute": attribute, "value": value, "fields": named}
        if replaced:
            replaced._set_payload(payload)
            return replaced
        return self._add_change(view, "set_attribute", xpath, "attributes", payload)

    def _update_field(self, view, op):
        name = op.get("field_name")
        change = self._field_add_change(view.model, name)
        if not change:
            raise UserError(
                self.env._("%(name)s is not a field of this project.", name=name)
            )
        payload = change._payload()
        definition = dict(payload.get("field") or {}, **(op.get("field") or {}))
        if definition.get("ttype") != payload["field"].get("ttype"):
            raise UserError(self.env._("The type of a field cannot change."))
        _name, definition = self._clean_field_definition(
            view.model, definition, name=name
        )
        payload["field"] = definition
        change._set_payload(payload)
        return change

    def _remove_node(self, view, arch, op):
        """Remove a node: one the project added leaves the project with the
        changes that name it; any other node is hidden, or removed from
        the arch in a view type whose hide mode is « remove »."""
        xpath = op.get("target")
        node = self._locate(arch, xpath)
        if node.getparent() is None:
            raise UserError(self.env._("The view itself cannot be removed."))
        added = self._added_changes(view, xpath)
        if added:
            changes = self._view_changes(view)
            keys = studio_arch.changes_on_added(
                self._base_arch(view),
                [c._as_dict() for c in changes],
                view.type,
                added.id,
            )
            (added | changes.filtered(lambda c: c.id in keys)).unlink()
            return added.browse()
        if studio_arch.hide_mode(view.type) == "remove":
            payload = {}
            field_name = studio_arch.shown_field_name(view.type, node)
            if field_name:
                payload["field_name"] = field_name
            elif node.get("name"):
                payload["node_name"] = node.get("name")
            return self._add_change(view, "remove", xpath, "replace", payload)
        self._refuse(studio_arch.hide_refusal(view.type, node))
        return self._attribute_operation(
            view, arch, {"type": "hide", "target": xpath, "value": True}
        )

    def action_undo(self, view=None):
        """Remove the last change (of ``view`` when given)."""
        self._check_studio_access()
        for project in self._editing():
            changes = project._view_changes(view) if view else project.change_ids
            last = changes.sorted(lambda c: (c.sequence, c.id))[-1:]
            last.unlink()
            project._touch()
        return True

    def action_discard(self):
        """Back to the changes of the last Apply; no Apply: no change."""
        self._check_studio_access()
        for project in self._editing():
            snapshot = json.loads(project.applied_snapshot or "[]")
            project.change_ids.unlink()
            Change = project.env["erplibre.studio.change"]
            for index, item in enumerate(snapshot):
                Change.create(
                    {
                        "project_id": project.id,
                        "sequence": (index + 1) * 10,
                        "change_type": item["type"],
                        "model": item["model"],
                        "view_id": item["view_id"],
                        "view_type": item["view_type"],
                        "xpath": item["xpath"],
                        "position": item["position"],
                        "payload": json.dumps(item["payload"], sort_keys=True),
                    }
                )
            project._touch()
        return True

    # ── apply / revert ──────────────────────────────────────────────────

    def _studio_xmlname(self, view):
        xml_id = view.xml_id
        base = xml_id.replace(".", "_") if xml_id else f"view_{view.id}"
        return f"{base}_studio"

    def _studio_view(self, view):
        """The inherited view of the project on ``view``, by its external id
        under the module name."""
        data = (
            self.env["ir.model.data"]
            .sudo()
            .search(
                [
                    ("module", "=", self.module_name),
                    ("name", "=", self._studio_xmlname(view)),
                    ("model", "=", "ir.ui.view"),
                ],
                limit=1,
            )
        )
        return self.env["ir.ui.view"].sudo().browse(data.res_id).exists()

    def _rename_studio_xmlids(self, new_name):
        self.ensure_one()
        self.env["ir.model.data"].sudo().search(
            [
                ("module", "=", self.module_name),
                ("model", "=", "ir.ui.view"),
                ("res_id", "in", self.studio_view_ids.ids),
            ]
        ).write({"module": new_name})

    def _field_vals(self, model, name, definition):
        vals = {
            "field_description": definition["field_description"],
            "readonly": definition.get("readonly", False),
            "help": definition.get("help") or False,
        }
        if definition["ttype"] == "selection":
            vals["selection"] = repr([tuple(item) for item in definition["selection"]])
        elif definition["ttype"] == "many2one":
            vals["relation"] = definition["relation"]
        elif definition["ttype"] == "monetary":
            vals["currency_field"] = definition["currency_field"]
        return vals

    def _apply_fields(self, log):
        """Create or update the ``x_`` fields of the project. Return (fields
        kept, names of the fields whose new definition waits for the
        module): a field the generated module defines, once installed,
        changes with the module only."""
        Fields = self.env["ir.model.fields"].sudo()
        kept = Fields
        waiting = []
        for change in self._project_field_changes():
            payload = change._payload()
            name, definition = payload["field_name"], payload["field"]
            vals = self._field_vals(change.model, name, definition)
            field = Fields._get(change.model, name)
            if not field:
                vals.update(
                    {
                        "name": name,
                        "model": change.model,
                        "model_id": self.env["ir.model"]._get_id(change.model),
                        "ttype": definition["ttype"],
                        "state": "manual",
                    }
                )
                field = Fields.create(vals)
                log.append(f"field {change.model}.{name}: created")
            elif field.state == "manual":
                if field.ttype != definition["ttype"]:
                    raise UserError(
                        self.env._(
                            "The field %(name)s exists with another type.",
                            name=name,
                        )
                    )
                todo = self._field_differences(field, vals)
                if todo:
                    field.write(todo)
                    log.append(f"field {change.model}.{name}: updated")
            elif self._module_of("ir.model.fields", field.id) == self.module_name:
                if self._field_differences(field, vals):
                    waiting.append(f"{change.model}.{name}")
                    log.append(
                        f"field {change.model}.{name}: defined by the module, "
                        "changes with its next generation and upgrade"
                    )
            else:
                log.append(
                    f"field {change.model}.{name}: owned by a module, left as is"
                )
            kept |= field
        return kept, waiting

    @api.model
    def _module_of(self, model_name, res_id):
        """The module of the first external id of the record ``res_id`` of
        ``model_name``, or False."""
        data = (
            self.env["ir.model.data"]
            .sudo()
            .search(
                [("model", "=", model_name), ("res_id", "=", res_id)],
                order="id",
                limit=1,
            )
        )
        return data.module or False

    @api.model
    def _field_differences(self, field, vals):
        """The values of ``vals`` (``_field_vals``) that ``field`` lacks."""
        current = {k: field[k] for k in vals if k != "selection"}
        if "selection" in vals:
            current["selection"] = repr(
                [(s.value, s.name) for s in field.selection_ids]
            )
        return {k: v for k, v in vals.items() if current.get(k) != v}

    def _apply_views(self, log):
        View = self.env["ir.ui.view"].sudo()
        kept = View
        for view in self.change_ids.mapped("view_id"):
            changes = [c._as_dict() for c in self._view_changes(view)]
            vals = {
                "name": f"{self.module_name}.{self._studio_xmlname(view)}",
                "model": view.model,
                "inherit_id": view.id,
                "mode": "extension",
                "priority": STUDIO_PRIORITY,
                "arch": studio_arch.view_arch(changes, view.type),
            }
            studio_view = self._studio_view(view)
            if studio_view:
                studio_view.write(vals)
                log.append(f"view {vals['name']}: updated")
            else:
                studio_view = View.create(vals)
                self.env["ir.model.data"].sudo().create(
                    {
                        "module": self.module_name,
                        "name": self._studio_xmlname(view),
                        "model": "ir.ui.view",
                        "res_id": studio_view.id,
                    }
                )
                log.append(f"view {vals['name']}: created")
            kept |= studio_view
        return kept

    def action_apply(self):
        """Write the changes into the database: the new fields, then one
        inherited view per edited view. Applying again updates them.
        Return True, or a warning notification that names the fields whose
        new definition waits for the next generation of the installed
        module."""
        self._check_studio_access()
        waiting = []
        for project in self:
            log = []
            views_before = project.studio_view_ids
            fields_before = project.field_ids
            kept_fields, waiting_fields = project._apply_fields(log)
            waiting += waiting_fields
            kept_views = project._apply_views(log)
            obsolete_views = (views_before - kept_views).exists()
            if obsolete_views:
                obsolete_views.unlink()
                log.append(f"{len(obsolete_views)} view(s) removed")
            obsolete_fields = (
                (fields_before - kept_fields)
                .exists()
                .filtered(lambda f: f.state == "manual")
            )
            if obsolete_fields:
                obsolete_fields.unlink()
                log.append(f"{len(obsolete_fields)} field(s) removed")
            project._internal().write(
                {
                    "field_ids": [(6, 0, kept_fields.ids)],
                    "studio_view_ids": [(6, 0, kept_views.ids)],
                    "applied_snapshot": project._current_snapshot(),
                    "applied_date": fields.Datetime.now(),
                }
            )
            project._touch()
            _logger.info("Studio project %s applied: %s", project.module_name, log)
        if not waiting:
            return True
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "warning",
                "sticky": True,
                "title": self.env._("Applied"),
                "message": self.env._(
                    "The installed generated module defines these fields: "
                    "their new definition takes effect once the module is "
                    "regenerated and upgraded: %(fields)s",
                    fields=", ".join(waiting),
                ),
                "next": {"type": "ir.actions.client", "tag": "soft_reload"},
            },
        }

    def action_revert(self):
        """Remove from the database the views and the custom fields the
        project created; the changes stay, as a draft."""
        self._check_studio_access()
        for project in self:
            views = project.studio_view_ids.exists()
            self.env["ir.model.data"].sudo().search(
                [("model", "=", "ir.ui.view"), ("res_id", "in", views.ids)]
            ).unlink()
            views.unlink()
            project.field_ids.exists().filtered(lambda f: f.state == "manual").unlink()
            project._internal().write(
                {
                    "field_ids": [(5, 0, 0)],
                    "studio_view_ids": [(5, 0, 0)],
                    "applied_snapshot": False,
                    "applied_date": False,
                }
            )
            project._touch()
        return True

    def action_open_editor(self):
        """The editor on the first view the project changes."""
        self.ensure_one()
        view = self.change_ids[:1].view_id
        if not view:
            raise UserError(
                self.env._("Open the editor from the debug menu of a view.")
            )
        return self.env["erplibre.studio.editor"].action_customize(
            view.model, view.id, view.type, project_id=self.id
        )


def etree_placeholder(label, note):
    """The form element that stands for a field not yet created."""
    div = etree.Element(
        "div",
        {"class": "alert alert-info py-1 px-2 mb-1 o_erplibre_studio_pending"},
    )
    strong = etree.SubElement(div, "strong")
    strong.text = label
    span = etree.SubElement(div, "span", {"class": "text-muted ms-1"})
    span.text = f"({note})"
    return div


def remove_keeping_tail(node):
    """Remove ``node`` from its parent; the text that follows it stays."""
    parent = node.getparent()
    if node.tail:
        previous = node.getprevious()
        if previous is not None:
            previous.tail = (previous.tail or "") + node.tail
        else:
            parent.text = (parent.text or "") + node.tail
    parent.remove(node)
