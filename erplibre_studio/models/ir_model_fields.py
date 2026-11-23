# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""The custom properties fields of the studio projects.

A ``fields.Properties`` reads its definition through a many2one of its
model and a ``fields.PropertiesDefinition`` of the comodel, given as
``definition="<many2one>.<field>"``. ``ir.model.fields`` has no column for
it: Odoo builds a custom properties row with ``definition=None``, and its
first read calls ``record[None]``. The rows Apply creates carry
``erplibre_studio_properties_definition``; this module builds them with
that definition, and leaves out of the registry, with a warning, a row
whose definition is missing, malformed or names fields the registry does
not have: such a field would make every form of its model fail."""

import inspect
import logging
import re

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# « many2one.field »: two field names.
DEFINITION_PATTERN = re.compile(r"^[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*$")


class IrModelFields(models.Model):
    _inherit = "ir.model.fields"

    erplibre_studio_properties_definition = fields.Char(
        string="Studio properties definition",
        readonly=True,
        copy=False,
        help="For a custom properties field of ERPLibre studio: the many2one "
        "of the model and the properties definition field of its comodel it "
        "reads its definition from, written « many2one.field ».",
    )

    def _instanciate_attrs(self, field_data):
        """The attributes of a custom field; for a properties field, its
        ``definition`` read from ``erplibre_studio_properties_definition``,
        and None (the field is not loaded) when that value is missing or
        malformed. The value is read with ``get``: the column does not
        exist yet while this module installs."""
        attrs = super()._instanciate_attrs(field_data)
        if not attrs or field_data["ttype"] != "properties":
            return attrs
        value = field_data.get("erplibre_studio_properties_definition") or ""
        if not DEFINITION_PATTERN.match(value):
            _logger.warning(
                "Properties field %s.%s not loaded: no valid definition (%r)",
                field_data["model"],
                field_data["name"],
                value,
            )
            return None
        attrs["definition"] = value
        return attrs

    def _add_manual_fields(self, model):
        """Load the custom fields of ``model``, then leave out each custom
        properties field whose definition the registry cannot resolve: its
        many2one is not a many2one of ``model``, or the comodel has no
        properties definition field of that name
        (``_studio_definition_field``)."""
        super()._add_manual_fields(model)
        for name, data in self._get_manual_field_data(model._name).items():
            field = model._fields.get(name)
            if data["ttype"] != "properties" or field is None or not field.manual:
                continue
            container = model._fields.get(field.definition_record or "")
            if container is None or container.type != "many2one":
                problem = "its container is not a many2one of the model"
            elif not self._studio_definition_field(
                model, container.comodel_name, field.definition_record_field
            ):
                problem = "the comodel has no properties definition field of that name"
            else:
                continue
            model._pop_field(name)
            _logger.warning(
                "Properties field %s.%s not loaded: %s (%s)",
                model._name,
                name,
                problem,
                field.definition,
            )

    @api.model
    def _studio_definition_field(self, model, comodel, name):
        """Whether ``comodel`` has the properties definition field ``name``:
        a ``fields.PropertiesDefinition`` of its classes, or a custom row
        of type « properties_definition ». The comodel may not be set up
        yet: its classes and its rows answer, not its ``_fields``."""
        if not name or comodel not in model.pool:
            return False
        static = inspect.getattr_static(model.pool[comodel], name, None)
        if isinstance(static, fields.PropertiesDefinition):
            return True
        data = self._get_manual_field_data(comodel).get(name)
        return bool(data and data["ttype"] == "properties_definition")
