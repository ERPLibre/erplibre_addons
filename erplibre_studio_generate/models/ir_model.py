# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""The custom models of the studio projects whose name has no ``x_``.

Odoo refuses such a name at the creation of a custom model only
(``_check_model_name``); at every setup of the registry it builds every
row of state « manual » (``_add_manual_models``), whatever its name. The
rows Apply creates without the prefix carry ``erplibre_studio_unprefixed``:
this module lets those, and only those, pass the core rule while the rule
of the database allows it (``_studio_model_name_rule``). Unlike a field,
such a model keeps loading without this module; what the module adds at
loading is the protection against a module installed later that defines
a model of the same name: the custom row would be built again in place of
the class of that module, which takes its table over instead."""

import logging

from odoo import api, fields, models
from odoo.addons.erplibre_studio import arch as studio_arch
from odoo.exceptions import ValidationError
from odoo.models import check_object_name
from odoo.tools import sql

_logger = logging.getLogger(__name__)


class IrModel(models.Model):
    _inherit = "ir.model"

    erplibre_studio_unprefixed = fields.Boolean(
        string="Studio name without x_",
        readonly=True,
        copy=False,
        help="A model of an ERPLibre studio project whose name has no x_: "
        "ERPLibre studio generate protects it from a module of the same name "
        "installed later.",
    )

    @api.constrains("model")
    def _check_model_name(self):
        """A custom model that carries the mark and has no ``x_`` needs the
        development rule and a name ``model_name_refusal`` accepts without
        the prefix; the other rows keep the core rule, ``x_`` for a custom
        model (a row created without the mark included)."""
        marked = self.filtered(
            lambda m: m.state == "manual"
            and m.erplibre_studio_unprefixed
            and not m.model.startswith("x_")
        )
        if marked:
            rule = self.env["erplibre.studio.project"]._studio_model_name_rule()
            for record in marked:
                refusal = studio_arch.model_name_refusal(
                    record.model, prefix_required=False
                )
                if (
                    rule["prefix_required"]
                    or refusal is not None
                    or not check_object_name(record.model)
                ):
                    raise ValidationError(
                        self.env._(
                            "The model name %(name)s needs the prefix x_ on "
                            "this database, or does not fit the rule of the "
                            "models without x_.",
                            name=record.model,
                        )
                    )
        return super(IrModel, self - marked)._check_model_name()

    def _add_manual_models(self):
        """Before the custom models are built, a marked row whose name a
        module of the registry defines now becomes that module's (state
        « base »), as the take-over hook of a generated module does: built
        again, the custom model would replace the class of the module. Its
        table and records stay. The mark is read only once its column
        exists: it does not while this module installs."""
        cr = self.env.cr
        if sql.column_exists(cr, "ir_model", "erplibre_studio_unprefixed"):
            cr.execute(
                "SELECT model FROM ir_model "
                "WHERE state = 'manual' AND erplibre_studio_unprefixed"
            )
            taken = [
                name
                for (name,) in cr.fetchall()
                if name in self.pool and not self.pool[name]._custom
            ]
            for name in taken:
                self._studio_log_taken_over(name)
            if taken:
                cr.execute(
                    "UPDATE ir_model SET state = 'base' WHERE model IN %s",
                    [tuple(taken)],
                )
        return super()._add_manual_models()

    @api.model
    def _studio_log_taken_over(self, name):
        """Log the custom model ``name`` that a module defines now: at the
        level info when that module is the generated module of a studio
        project (its installation takes the model over), else as a
        warning, since another module now owns the table."""
        module = self.pool[name]._module
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
            "Studio model %s is defined by the module %s now: the module takes "
            "its table over",
            name,
            module,
        )
