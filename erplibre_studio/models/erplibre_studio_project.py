# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import json
import logging

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


class ViewExclusion(tuple):
    """The ids of the views left out of a combined arch (``EXCLUDE_KEY``).
    A Python type that no RPC call can build: a list sent by a client in
    its context is ignored, so the shared view cache never holds an arch
    without the views of the modules."""


class ErplibreStudioProject(models.Model):
    """A studio project: the changes of form and list views that make one
    module. Its life: draft changes (previewed by its editor only), then
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
        shows as a placeholder in a form and is left out of a list."""
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
            if view.type == "list":
                parent.remove(node)
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

    def _check_drop(self, arch, op, view_type):
        target = op.get("target")
        position = op.get("position") or "after"
        if position not in studio_arch.POSITIONS:
            raise UserError(self.env._("Unknown position %(pos)s.", pos=position))
        node = self._locate(arch, target)
        drops = studio_arch.DROP_CONTAINERS[view_type]
        if position == "inside" and node.tag not in drops:
            raise UserError(
                self.env._("A field cannot be dropped inside <%(tag)s>.", tag=node.tag)
            )
        parent = node.getparent()
        if position != "inside" and (parent is None or parent.tag not in drops):
            raise UserError(self.env._("A field cannot be dropped there."))
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
        if code == "no_node":
            return self.env._("No node at %(xpath)s.", **params)
        if code == "invalid_xpath":
            return self.env._("Invalid XPath %(xpath)s: %(error)s", **params)
        if code == "unknown_change":
            return self.env._("Unknown change type %(type)s.", **params)
        if code == "unknown_position":
            return self.env._("Unknown position %(position)s.", **params)
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

    def _apply_operation(self, view, op):
        """Record the editor operation ``op`` (a dict with a ``type``) on
        ``view`` as a change, or update the change it refines. Return the
        change touched, or an empty recordset. Raise UserError when the
        operation does not fit the draft arch."""
        self.ensure_one()
        self = self._editing()
        if view.type not in studio_arch.VIEW_TYPES:
            raise UserError(self.env._("The studio edits form and list views only."))
        arch, _errors = self._draft_arch(view)
        otype = op.get("type")
        Change = self.env["erplibre.studio.change"]
        change = Change
        if otype == "add_field":
            target, position, _node = self._check_drop(arch, op, view.type)
            name, definition = self._clean_field_definition(
                view.model, op.get("field") or {}
            )
            change = self._add_change(
                view,
                "add_field",
                target,
                position,
                {"field_name": name, "field": definition, "node_attrs": {}},
            )
        elif otype == "add_existing_field":
            target, position, _node = self._check_drop(arch, op, view.type)
            name = op.get("field_name")
            if name not in self.env[view.model]._fields:
                raise UserError(self.env._("Unknown field %(name)s.", name=name))
            if arch.xpath(f"//field[@name='{name}']"):
                raise UserError(
                    self.env._("The field %(name)s is already in the view.", name=name)
                )
            change = self._add_change(
                view,
                "add_existing_field",
                target,
                position,
                {"field_name": name, "node_attrs": {}},
            )
        elif otype == "move":
            target, position, node = self._check_drop(arch, op, view.type)
            source = self._locate(arch, op.get("source"))
            if source is node or source in node.iterancestors():
                raise UserError(self.env._("A node cannot move into itself."))
            change = self._add_change(
                view,
                "move",
                target,
                position,
                {"source": op.get("source"), "field_name": source.get("name")},
            )
        elif otype == "update_field":
            change = self._update_field(view, op)
        elif otype == "remove":
            change = self._remove_node(view, arch, op)
        elif otype in ("hide",) + tuple(studio_arch.ATTRIBUTE_CHANGES):
            change = self._attribute_operation(view, arch, op)
        else:
            raise UserError(self.env._("Unknown operation %(type)s.", type=otype))
        self._touch()
        if change.exists():
            _arch, errors = self._draft_arch(view)
            if change.id in errors:
                raise UserError(errors[change.id])
        return change.exists()

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
        changes = self._view_changes(view)
        existing = changes.filtered(
            lambda c: c.change_type == otype and c.xpath == xpath
        )
        # The change a new value replaces: by name, the latest one; by
        # position, only the last change of the view, since a later change
        # may have moved what the position names.
        replaced = existing[-1:]
        if replaced and not xpath.startswith("//") and replaced != changes[-1:]:
            replaced = existing.browse()
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
        """Remove a node: a field added by the project leaves the project
        with the changes that name it; any other node is hidden."""
        xpath = op.get("target")
        node = self._locate(arch, xpath)
        name = node.get("name") if node.tag == "field" else None
        added = self._view_changes(view).filtered(
            lambda c: c.change_type in studio_arch.ADD_CHANGES and c.field_name == name
        )
        if not name or not added:
            return self._attribute_operation(
                view, arch, {"type": "hide", "target": xpath, "value": True}
            )
        marker = f"@name='{name}'"
        later = self._view_changes(view).filtered(
            lambda c: c.sequence > added[0].sequence
            and (marker in (c.xpath or "") or c.field_name == name)
        )
        (added | later).unlink()
        return added.browse()

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
                self.env._("Open the editor from the debug menu of a form or a list.")
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
