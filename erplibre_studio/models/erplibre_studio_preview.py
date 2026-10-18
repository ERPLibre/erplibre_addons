# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import ast
import copy
import json
import logging
import threading
import time
from contextlib import contextmanager

import psycopg2
from lxml import etree
from odoo import Command, fields, models
from odoo.exceptions import UserError

from .. import arch as studio_arch
from .erplibre_studio_project import (
    MODEL_VIEW_PRIORITY,
    etree_placeholder,
    remove_keeping_tail,
)
from .studio_pending import pending_view

_logger = logging.getLogger(__name__)

# One real preview at a time in a process: the models it creates for the
# time of the render are in the registry of the process, which the threads
# of a threaded server share.
_REAL_PREVIEW_LOCK = threading.Lock()

# The longest the real preview waits for a lock, and runs a statement: a
# table another transaction writes makes it fail fast.
LOCK_TIMEOUT = "2s"
STATEMENT_TIMEOUT = "15s"

# The field types fields_get says the records can be grouped by.
GROUPABLE_TYPES = (
    "char",
    "selection",
    "many2one",
    "date",
    "datetime",
    "boolean",
    "integer",
    "float",
    "monetary",
)
# The types whose values the records add up, as Odoo does for its numbers.
SUM_TYPES = ("integer", "float", "monetary")
# The options a relational field of a preview gets: no record of its comodel
# is created nor opened from it, the preview saves nothing.
PREVIEW_FIELD_OPTIONS = {"no_create": True, "no_create_edit": True, "no_open": True}


class StudioPreviewError(Exception):
    """A real preview that could not render: its message is the answer."""


def _field_info(name, ttype, string, **extra):
    """A field description in the shape of ``fields_get``."""
    stored = extra.pop("store", True)
    info = {
        "name": name,
        "type": ttype,
        "string": string,
        "required": False,
        "readonly": False,
        "help": "",
        "store": stored,
        "searchable": True,
        "sortable": stored and ttype not in studio_arch.X2MANY_TYPES,
        "groupable": stored and ttype in GROUPABLE_TYPES,
        "aggregator": "sum" if ttype in SUM_TYPES else False,
        "relation": False,
        "selection": [],
        "context": {},
        "domain": [],
        "translate": False,
    }
    info.update(extra)
    return info


class ErplibreStudioProject(models.Model):
    """The preview of a model the project does not create yet. Simulation:
    its views and fields computed from the lines of the draft, nothing
    written, any database. Real, once the draft is approved: the model and
    its views created inside a savepoint, rendered by get_views, then
    everything rolled back."""

    _inherit = "erplibre.studio.project"

    # ── simulation ──────────────────────────────────────────────────────

    def _studio_simulated_fields(self, line):
        """{name: fields_get description} of the model of the line ``line``,
        not created yet: the fields Odoo gives a custom model, ``x_name``,
        and the new fields of the project on it (inverse many2one
        included)."""
        self.ensure_one()
        fields_info = {
            "id": _field_info("id", "integer", "ID", readonly=True),
            "display_name": _field_info(
                "display_name", "char", "Display Name", readonly=True, store=False
            ),
            "x_name": _field_info("x_name", "char", "Name", required=True),
            "create_date": _field_info(
                "create_date", "datetime", "Created on", readonly=True
            ),
            "write_date": _field_info(
                "write_date", "datetime", "Last Updated on", readonly=True
            ),
            "create_uid": _field_info(
                "create_uid",
                "many2one",
                "Created by",
                readonly=True,
                relation="res.users",
            ),
            "write_uid": _field_info(
                "write_uid",
                "many2one",
                "Last Updated by",
                readonly=True,
                relation="res.users",
            ),
        }
        for name, (definition, _change) in self._studio_field_definitions(
            line.model
        ).items():
            ttype = definition.get("ttype")
            extra = {
                "readonly": bool(definition.get("readonly")),
                "help": definition.get("help") or "",
                "relation": definition.get("relation") or False,
                "selection": definition.get("selection") or [],
            }
            if ttype == "one2many":
                extra["relation_field"] = definition.get("relation_field")
            if ttype == "monetary":
                extra["currency_field"] = definition.get("currency_field")
            fields_info[name] = _field_info(
                name, ttype, definition.get("field_description") or name, **extra
            )
        return fields_info

    def _studio_preview_arch(self, arch, fields_info=None):
        """``arch`` (an element) with its chatter replaced by a placeholder:
        the chatter would call the routes of mail on a model that does not
        exist. Its many2one and many2many fields of ``fields_info`` (name:
        fields_get description) get PREVIEW_FIELD_OPTIONS, merged into the
        options of the node when they read as a dict."""
        for node in arch.iter("field"):
            info = (fields_info or {}).get(node.get("name")) or {}
            if info.get("type") not in ("many2one", "many2many"):
                continue
            if any(a.tag == "field" for a in node.iterancestors()):
                continue
            try:
                options = ast.literal_eval(node.get("options") or "{}")
            except (ValueError, SyntaxError):
                continue
            if isinstance(options, dict):
                node.set("options", repr({**options, **PREVIEW_FIELD_OPTIONS}))
        for node in list(arch.iter("chatter")) + arch.xpath(
            "//div[contains(concat(' ', normalize-space(@class), ' '), ' oe_chatter ')]"
        ):
            placeholder = etree_placeholder(
                self.env._("Chatter"),
                self.env._("messages and activities, created by Apply"),
            )
            placeholder.tail = node.tail
            node.getparent().replace(node, placeholder)
        return arch

    def _studio_comodel_fields(self, model, names):
        """The fields_get descriptions of the fields ``names`` of ``model``,
        a model of the registry, or simulated for a model of the project
        not created yet."""
        line = self._studio_pending_line(model)
        if line:
            return self._studio_simulated_fields(line)
        Model = self.env[model]
        wanted = [n for n in {"id", "display_name", *names} if n in Model._fields]
        return Model.fields_get(
            wanted, attributes=self.env["ir.ui.view"]._get_view_field_attributes()
        )

    def _studio_simulated_views(self, line):
        """The answer of the simulation of the model line ``line``, in the
        shape of get_views: {mode, model, views: {type: {arch, id}}, models:
        {model: {fields}}, defaults, model_defaults, pending_models,
        approved}. A read: nothing is written, no savepoint is opened."""
        self.ensure_one()
        own = self._studio_simulated_fields(line)
        views = {}
        comodels = {}
        for view_type in studio_arch.MODEL_VIEW_TYPES:
            arch, _errors = self._draft_arch(pending_view(line, view_type))
            arch = self._studio_preview_arch(arch, own)
            for node in arch.iter("field"):
                parent = next(
                    (a for a in node.iterancestors() if a.tag == "field"), None
                )
                if parent is not None:
                    info = own.get(parent.get("name")) or {}
                    if info.get("relation"):
                        comodels.setdefault(info["relation"], set()).add(
                            node.get("name")
                        )
                    continue
                info = own.get(node.get("name")) or {}
                if info.get("relation"):
                    comodels.setdefault(info["relation"], set())
            views[view_type] = {
                "arch": etree.tostring(arch, encoding="unicode"),
                "id": False,
            }
        models_info = {line.model: {"fields": own}}
        for comodel, names in comodels.items():
            if comodel != line.model:
                models_info[comodel] = {
                    "fields": self._studio_comodel_fields(comodel, names)
                }
        pending = [m for m in models_info if m not in self.env]
        model_defaults = {
            model: {
                name: [] if info.get("type") in studio_arch.X2MANY_TYPES else False
                for name, info in models_info[model]["fields"].items()
                if not info.get("readonly")
            }
            for model in pending
        }
        return {
            "mode": "simulation",
            "model": line.model,
            "views": views,
            "models": models_info,
            "defaults": model_defaults.get(line.model, {}),
            "model_defaults": model_defaults,
            "pending_models": pending,
            "approved": self.approved,
        }

    # ── approval ────────────────────────────────────────────────────────

    def _studio_preview_snapshot(self):
        """The JSON of what the real preview creates: the models not created
        yet (technical name, label, chatter), the changes of their default
        views and their new fields."""
        self.ensure_one()
        lines = self.new_model_ids.filtered(lambda line: not line.applied)
        names = set(lines.mapped("model"))
        changes = self.change_ids.filtered(lambda c: c.model_line_id in lines)
        definitions = {
            line.model: {
                name: definition
                for name, (definition, _change) in self._studio_field_definitions(
                    line.model
                ).items()
            }
            for line in lines
        }
        return json.dumps(
            {
                "models": [
                    {"model": line.model, "name": line.name, "chatter": line.chatter}
                    for line in lines.sorted("model")
                ],
                "changes": changes._snapshot(),
                "fields": definitions,
                "names": sorted(names),
            },
            sort_keys=True,
        )

    def action_approve(self):
        """Approve the models not created yet for a real preview: the user
        and the date are recorded, with what the real preview creates; any
        change of it withdraws the approval."""
        self._check_studio_access()
        for project in self:
            if not project.new_model_ids.filtered(lambda line: not line.applied):
                raise UserError(
                    self.env._(
                        "The project has no model waiting for Apply: there is "
                        "nothing to preview."
                    )
                )
            project._internal().write(
                {
                    "approved_snapshot": project._studio_preview_snapshot(),
                    "approved_uid": self.env.uid,
                    "approved_date": fields.Datetime.now(),
                }
            )
        return True

    def action_unapprove(self):
        """Withdraw the approval of the real preview."""
        self._check_studio_access()
        self._internal().write(
            {"approved_snapshot": False, "approved_uid": False, "approved_date": False}
        )
        return True

    # ── real preview ────────────────────────────────────────────────────

    @contextmanager
    def _studio_sandbox(self):
        """Run the block inside a savepoint that is always rolled back, and
        leave the registry, its caches, the callbacks of the cursor and the
        invalidation flags of the thread as they were: the end of the
        request then signals no change to the other workers, and nothing
        was committed for them to load. A statement that waits for a lock
        longer than LOCK_TIMEOUT, or runs longer than STATEMENT_TIMEOUT,
        fails."""
        env = self.env
        cr = env.cr
        registry = env.registry
        if registry.registry_invalidated:
            raise UserError(
                self.env._(
                    "This request changed the models of the database: reload the "
                    "editor before a real preview."
                )
            )
        cache_flags = set(registry.cache_invalidated)
        queue = len(registry._constraint_queue)
        callbacks = {
            name: (copy.copy(getattr(cr, name)._funcs), dict(getattr(cr, name).data))
            for name in ("postcommit", "prerollback", "postrollback")
        }
        env.flush_all()
        savepoint = cr.savepoint()
        try:
            cr.execute(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'")
            cr.execute(f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT}'")
            yield
        finally:
            savepoint.close(rollback=True)
            env.invalidate_all()
            registry.setup_models(cr)
            registry._ordinary_tables = None
            while len(registry._constraint_queue) > queue:
                registry._constraint_queue.pop()
            for name, (funcs, data) in callbacks.items():
                container = getattr(cr, name)
                container._funcs.clear()
                container._funcs.extend(funcs)
                container.data.clear()
                container.data.update(data)
            registry.registry_invalidated = False
            registry.cache_invalidated.clear()
            registry.cache_invalidated.update(cache_flags)
            env.invalidate_all()

    def _studio_sandbox_models(self, lines):
        """Create, in the sandbox, the models of ``lines`` and their new
        fields, in the order of Apply; never a field on an existing model.
        Return the (model, name) of the fields created."""
        IrModel = self.env["ir.model"].sudo().with_context(lang=None)
        Fields = self.env["ir.model.fields"].sudo().with_context(lang=None)
        mail = self._studio_mail_available()
        for line in lines:
            vals = {
                "model": line.model,
                "name": (line.name or "").strip() or line.model,
                "state": "manual",
                "field_id": [
                    Command.create(
                        {
                            "name": "x_name",
                            "field_description": "Name",
                            "ttype": "char",
                            "required": True,
                            "copied": True,
                        }
                    )
                ],
            }
            if line.chatter and mail:
                vals.update(is_mail_thread=True, is_mail_activity=True)
            IrModel.create(vals)
        pending = set(lines.mapped("model"))
        created = set()
        for model, name, definition, _change in self._studio_all_definitions():
            if model not in pending:
                continue
            relation = definition.get("relation")
            if relation and relation not in self.env:
                continue
            if definition["ttype"] == "one2many" and (
                relation not in pending
                and definition.get("relation_field") not in self.env[relation]._fields
            ):
                continue
            if definition["ttype"] == "one2many" and relation in pending:
                if (relation, definition["relation_field"]) not in created:
                    continue
            vals = self._field_vals(model, name, definition)
            vals.update(
                {
                    "name": name,
                    "model": model,
                    "model_id": IrModel._get_id(model),
                    "ttype": definition["ttype"],
                    "state": "manual",
                }
            )
            Fields.create(vals)
            created.add((model, name))
        return created

    def _studio_real_views(self, line):
        """The answer of the real preview of the model line ``line``: the
        models of the project not created yet, their fields and the views
        of ``line`` with the draft applied, created in a sandbox
        (``_studio_sandbox``); the views and the fields as get_views
        validates and post-processes them, the defaults as default_get gives
        them. The render runs as the superuser: it shows the views and the
        fields as Odoo validates them, not what the groups of the draft would
        reach. Refused unless the project is approved and no other real
        preview runs in the process; {error} when a view does not render."""
        self.ensure_one()
        if not self.approved:
            raise UserError(
                self.env._(
                    "The draft changed since its approval, or was never "
                    "approved: approve it again for a real preview."
                )
            )
        if line.applied:
            raise UserError(
                self.env._("The model %(model)s exists already.", model=line.model)
            )
        if not _REAL_PREVIEW_LOCK.acquire(blocking=False):
            raise UserError(self.env._("Another real preview is running: try again."))
        start = time.monotonic()
        lang = self.env.user.lang
        try:
            with self._studio_sandbox():
                try:
                    with self.env.cr.savepoint():
                        result = self._studio_render_real(line, lang)
                except StudioPreviewError as exc:
                    result = {"error": str(exc)}
                except psycopg2.errors.LockNotAvailable:
                    result = {"error": self._studio_busy_message()}
                except psycopg2.errors.QueryCanceled:
                    result = {"error": self._studio_busy_message()}
                except Exception as exc:  # noqa: BLE001 - a view error is the answer
                    result = {"error": str(exc.args[0] if exc.args else exc)}
        finally:
            _REAL_PREVIEW_LOCK.release()
        _logger.info(
            "Studio real preview of %s (project %s) rolled back in %.3fs",
            line.model,
            self.module_name,
            time.monotonic() - start,
        )
        if "error" in result:
            return {"mode": "real", "model": line.model, **result}
        return result

    def _studio_busy_message(self):
        return self.env._("The database is busy: try the real preview again.")

    def _studio_render_real(self, line, lang):
        """Create the models and the views of the preview of ``line`` and
        render them; plain data only: nothing of it outlives the sandbox."""
        lines = self.new_model_ids.filtered(lambda m: not m.applied)
        created = self._studio_sandbox_models(lines)
        View = self.env["ir.ui.view"].sudo()
        definitions = self._studio_field_definitions(line.model)
        for view_type in studio_arch.MODEL_VIEW_TYPES:
            arch, _errors = self._draft_arch(pending_view(line, view_type))
            for node in list(arch.iter("field")):
                if any(a.tag == "field" for a in node.iterancestors()):
                    continue
                name = node.get("name")
                if name in definitions and (line.model, name) not in created:
                    # A field the preview cannot create: its comodel or its
                    # inverse is a model of the database.
                    if view_type == "form":
                        placeholder = etree_placeholder(
                            definitions[name][0].get("field_description") or name,
                            self.env._("new field, created by Apply"),
                        )
                        placeholder.tail = node.tail
                        node.getparent().replace(node, placeholder)
                    else:
                        remove_keeping_tail(node)
            View.create(
                {
                    "name": f"{line.model}.{view_type}",
                    "model": line.model,
                    "type": view_type,
                    "mode": "primary",
                    "priority": MODEL_VIEW_PRIORITY,
                    "arch": etree.tostring(arch, encoding="unicode"),
                }
            )
        # In sudo: the access rights of the draft exist from Apply only, and
        # the model of the sandbox has no record to protect.
        Model = self.env[line.model].sudo().with_context(lang=lang)
        try:
            result = Model.get_views(
                [(False, view_type) for view_type in studio_arch.MODEL_VIEW_TYPES]
            )
            defaults = Model.default_get(list(Model._fields))
        except (ValueError, UserError) as exc:
            raise StudioPreviewError(str(exc.args[0] if exc.args else exc)) from exc
        data = json.loads(json.dumps(result, default=str))
        own = data["models"][line.model]["fields"]
        for view in data["views"].values():
            arch = self._studio_preview_arch(etree.fromstring(view["arch"]), own)
            view["arch"] = etree.tostring(arch, encoding="unicode")
        for view in data["views"].values():
            view["id"] = False
        pending = [m for m in data["models"] if m in set(lines.mapped("model"))]
        values = {
            name: [] if info.get("type") in studio_arch.X2MANY_TYPES else False
            for name, info in data["models"][line.model]["fields"].items()
            if not info.get("readonly")
        }
        values.update(json.loads(json.dumps(defaults, default=str)))
        defaults = values
        return {
            "mode": "real",
            "model": line.model,
            "views": data["views"],
            "models": data["models"],
            "defaults": defaults,
            "model_defaults": {line.model: defaults},
            "pending_models": pending,
            "approved": True,
        }
