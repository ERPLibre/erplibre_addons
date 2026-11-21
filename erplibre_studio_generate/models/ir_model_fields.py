# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""The custom fields of the studio projects whose name has no ``x_``.

Odoo loads a custom field (state « manual ») into the registry only when
``_is_manual_name`` accepts its name, ``x_`` and nothing else: any other
row is logged as « Failed to load field » and skipped. The rows Apply
creates without the prefix carry ``erplibre_studio_unprefixed``; this
module loads those, and only those, while it is installed. A database
without this module never loads a custom field without ``x_``."""

import inspect
import logging

from odoo import api, fields, models
from odoo.addons.erplibre_studio import arch as studio_arch
from odoo.addons.erplibre_studio.models.erplibre_studio_project import (
    delegation_classes,
)
from odoo.tools import sql

_logger = logging.getLogger(__name__)

# The context key that holds the names ``_is_manual_name`` accepts besides
# ``x_``: a frozenset, set for the time of one ``_add_manual_fields``.
UNPREFIXED_KEY = "erplibre_studio_unprefixed_names"

# The core constraint on the names of the custom fields, which
# code_generator drops at its installation.
MANUAL_NAME_CONSTRAINT = "name_manual_field"
MANUAL_NAME_CONNAME = f"ir_model_fields_{MANUAL_NAME_CONSTRAINT}"

_MISSING = object()


def drop_manual_name_constraint(cr):
    """Drop ``name_manual_field`` from ir_model_fields when it is there.
    code_generator drops it at its installation, but a module installed
    after it that extends ``ir.model.fields`` adds it back before this
    module is loaded; from then on ``_add_sql_constraints`` leaves it
    out. Called at the installation and the upgrade of this module, and
    at the end of every loading of the modules (``_register_hook``)."""
    if sql.constraint_definition(cr, "ir_model_fields", MANUAL_NAME_CONNAME):
        sql.drop_constraint(cr, "ir_model_fields", MANUAL_NAME_CONNAME)
        _logger.info("Dropped the constraint %s", MANUAL_NAME_CONNAME)


def _attribute_owner(cls, name):
    """Whether ``name`` is an attribute of ``cls`` other than a field: a
    method or a class attribute, which a field of that name replaces."""
    value = inspect.getattr_static(cls, name, _MISSING)
    return value is not _MISSING and not isinstance(value, fields.Field)


class IrModelFields(models.Model):
    _inherit = "ir.model.fields"

    erplibre_studio_unprefixed = fields.Boolean(
        string="Studio name without x_",
        readonly=True,
        copy=False,
        help="A field of an ERPLibre studio project whose name has no x_: "
        "loaded by ERPLibre studio generate.",
    )

    @api.model
    def _is_manual_name(self, name):
        return super()._is_manual_name(name) or name in self.env.context.get(
            UNPREFIXED_KEY, ()
        )

    def _add_manual_fields(self, model):
        """Load the custom fields of ``model``, the marked rows without
        ``x_`` included. The names go in the context of both ``self`` (the
        currency check of a monetary field) and ``model``, whose
        ``_add_field`` reads ``_is_manual_name`` through its own
        environment."""
        names = self._studio_loadable_names(model)
        if not names:
            return super()._add_manual_fields(model)
        context = {UNPREFIXED_KEY: frozenset(names)}
        return super(IrModelFields, self.with_context(**context))._add_manual_fields(
            model.with_context(**context)
        )

    @api.model
    def _studio_loadable_names(self, model):
        """The names of the custom fields of ``model`` without ``x_`` that
        carry ``erplibre_studio_unprefixed`` and pass the checks of a new
        field: the format, a name that replaces no method or attribute of
        every model nor of a class the field lands on: the class of
        ``model`` and those of the models that inherit it by delegation,
        which copy it (``delegation_classes``). A marked row that fails a check is
        left out with a warning, then Odoo logs it as not loaded. A row
        whose name a module defines now is no longer loaded: the field of
        the module takes its column over. The mark is read with ``get``:
        the column does not exist yet while this module installs."""
        names = set()
        for name, data in self._get_manual_field_data(model._name).items():
            if name.startswith("x_") or not data.get("erplibre_studio_unprefixed"):
                continue
            if name in model._fields:
                self._studio_log_taken_over(model, name)
                continue
            classes = delegation_classes(model.pool, model._name)
            reserved = (
                {name}
                if any(
                    _attribute_owner(cls, name) for cls in (*classes, models.BaseModel)
                )
                else ()
            )
            refusal = studio_arch.field_name_refusal(
                name, prefix_required=False, reserved=reserved
            )
            if refusal is not None:
                _logger.warning(
                    "Studio field %s.%s not loaded: %s (%s)",
                    model._name,
                    name,
                    refusal.code,
                    refusal,
                )
                continue
            names.add(name)
        return names

    @api.model
    def _studio_log_taken_over(self, model, name):
        """Log the custom field ``name`` of ``model`` that a module defines
        now: at the level info when that module is the generated module of
        a studio project (its installation takes the field over), else as
        a warning, since another module now owns the column."""
        module = model._fields[name]._module
        cr = self.env.cr
        generated = False
        if module and sql.table_exists(cr, "erplibre_studio_project"):
            cr.execute(
                "SELECT 1 FROM erplibre_studio_project WHERE module_name = %s LIMIT 1",
                [module],
            )
            generated = bool(cr.rowcount)
        _logger.log(
            logging.INFO if generated else logging.WARNING,
            "Studio field %s.%s is defined by the module %s now: the studio "
            "field no longer loads",
            model._name,
            name,
            module,
        )

    def _register_hook(self):
        """Drop ``name_manual_field`` again once the registry holds this
        module: Odoo calls the hook at the end of every loading of the
        modules. An update of base (« -u base », « -u all ») sets base up
        alone first, without the override of ``_add_sql_constraints``, and
        adds the constraint back; it would require x_ from then on."""
        super()._register_hook()
        drop_manual_name_constraint(self.env.cr)

    def _add_sql_constraints(self):
        """Leave out ``name_manual_field`` while the database does not have
        it: code_generator drops it, and every installation or update of a
        module that extends ``ir.model.fields`` would add it back, after
        which Apply refuses the names without ``x_``. A database that has
        it keeps it as Odoo defines it."""
        cls = type(self)
        if sql.constraint_definition(self._cr, self._table, MANUAL_NAME_CONNAME):
            return super()._add_sql_constraints()
        declared = cls._sql_constraints
        cls._sql_constraints = [c for c in declared if c[0] != MANUAL_NAME_CONSTRAINT]
        try:
            return super()._add_sql_constraints()
        finally:
            cls._sql_constraints = declared
