#!/usr/bin/env python3
# © 2021-2025 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
import ast
import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

TARGET_MODEL_SELECTION = [
    ("project.project", "Project"),
    ("project.task", "Project task"),
    ("res.partner", "Contact"),
    ("sale.order", "Sale order"),
    ("sale.order.line", "Sale order line"),
    ("account.move", "Invoice / Journal entry"),
    ("account.move.line", "Invoice line"),
    ("crm.lead", "CRM lead/opportunity"),
    ("helpdesk.ticket", "Helpdesk ticket"),
    ("other", "Other (manual)"),
]


class DevopsCgSyncBind(models.Model):
    _name = "devops.cg.sync.bind"
    _description = "Code generator sync external binding (transform)"
    _order = "sequence, id"

    model_id = fields.Many2one(
        comodel_name="devops.cg.model",
        string="Mirror model",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(default=10)
    target_model = fields.Selection(
        selection=TARGET_MODEL_SELECTION,
        required=True,
        default="project.project",
        help="Odoo model this binding creates/links from each mirror row",
    )
    target_model_other = fields.Char(
        string="Other target model",
        help="Technical model name when target_model is 'Other'",
    )
    bind_field_reverse = fields.Char(
        help="Field on the mirror model that links back to the bound record",
    )
    rec_name_mode = fields.Selection(
        selection=[("field", "Single field"), ("format", "Format + vars")],
        default="field",
    )
    rec_name_field = fields.Char(
        string="rec_name field",
        help="Mirror field used as the bound record display name",
    )
    rec_name_format = fields.Char(
        string="rec_name format",
        help="printf-style format, e.g. '%s %s'",
    )
    rec_name_vars = fields.Char(
        string="rec_name vars",
        help="Comma-separated mirror field names for the format",
    )
    link_only = fields.Boolean(
        help="Only run this binding during the link pass",
    )
    ignore = fields.Boolean(help="Emit but skip this binding at runtime")
    bind_condition = fields.Char(
        help="Optional Odoo domain (Python list literal) filtering mirror"
        " rows",
    )
    bind_group_by = fields.Char(help="Mirror field to group rows by")
    sync_by_mirror_field = fields.Char(
        help="Override mirror field(s) used as the sync key",
    )
    method_call = fields.Char(
        help="Custom sync.data.transform method to call instead of the"
        " declarative binding (escape hatch; implement it in the generated"
        " module)",
    )
    method_extra_json = fields.Text(
        string="method extra (JSON)",
        help="Extra keys merged into the bind config for method_call, e.g."
        ' {"order_lines": [{"product_name": "x", "qty": 1,'
        ' "price_unit": 10}]}',
    )
    binding_ids = fields.One2many(
        comodel_name="devops.cg.sync.bind.field",
        inverse_name="bind_id",
        string="Field bindings",
    )
    default_ids = fields.One2many(
        comodel_name="devops.cg.sync.bind.default",
        inverse_name="bind_id",
        string="Default values",
    )

    def _build_rec_name(self):
        self.ensure_one()
        if self.rec_name_mode == "format" and self.rec_name_format:
            return {
                "string": self.rec_name_format,
                "vars": [
                    v.strip()
                    for v in (self.rec_name_vars or "").split(",")
                    if v.strip()
                ],
            }
        return self.rec_name_field or ""

    def _parse_bind_condition(self):
        self.ensure_one()
        try:
            return ast.literal_eval(self.bind_condition)
        except (ValueError, SyntaxError):
            _logger.warning(
                "Invalid bind_condition on bind %s: %s",
                self.id,
                self.bind_condition,
            )
            return self.bind_condition

    def _build_bind_config(self):
        self.ensure_one()
        config = {}
        if self.bind_field_reverse:
            config["bind_field_reverse"] = self.bind_field_reverse
        if self.method_call:
            config["method_call"] = self.method_call
            if self.method_extra_json:
                try:
                    config.update(json.loads(self.method_extra_json))
                except (ValueError, TypeError):
                    _logger.warning(
                        "Invalid method_extra_json on bind %s", self.id
                    )
        else:
            target = (
                self.target_model_other
                if self.target_model == "other"
                else self.target_model
            )
            model_cfg = {
                "binding": [
                    b._build_binding_entry() for b in self.binding_ids
                ],
                "default_field": {
                    d.key: d._coerce_value() for d in self.default_ids if d.key
                },
            }
            rec_name = self._build_rec_name()
            if rec_name:
                model_cfg["rec_name"] = rec_name
            config["bind_field_model"] = {target: model_cfg}
        if self.link_only:
            config["link_only"] = True
        if self.ignore:
            config["ignore"] = True
        if self.bind_condition:
            config["bind_condition"] = self._parse_bind_condition()
        if self.bind_group_by:
            # Engine reads bind_group_by[0]; emit a list of field names.
            config["bind_group_by"] = [self.bind_group_by]
        if self.sync_by_mirror_field:
            # Engine uses this as the sync-key list (like metadata["sync"]).
            config["sync_by_mirror_field"] = [
                v.strip()
                for v in self.sync_by_mirror_field.split(",")
                if v.strip()
            ]
        return config

    @api.constrains("target_model", "target_model_other", "method_call")
    def _check_target_model_other(self):
        for rec in self:
            if (
                not rec.method_call
                and rec.target_model == "other"
                and not rec.target_model_other
            ):
                raise ValidationError(
                    _(
                        "A binding with target model 'Other' requires"
                        " 'Other target model' to be set."
                    )
                )


class DevopsCgSyncBindField(models.Model):
    _name = "devops.cg.sync.bind.field"
    _description = "Code generator sync external binding - field mapping"
    _order = "sequence, id"

    bind_id = fields.Many2one(
        comodel_name="devops.cg.sync.bind",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(default=10)
    field_name = fields.Char(
        required=True,
        help="Field on the bound (target) model to set",
    )
    mirror_field_id = fields.Many2one(
        comodel_name="devops.cg.field",
        string="Mirror field",
        ondelete="cascade",
        help="Source field on the mirror model",
    )
    is_sync = fields.Boolean(
        help="This field is the search key for the bound record",
    )
    search_field_name = fields.Char(
        help="For many2one targets: comodel field to search on",
    )
    compute_field = fields.Char(
        help="Custom method name to resolve a many2one value",
    )

    def _build_binding_entry(self):
        self.ensure_one()
        entry = {
            "field_name": self.field_name,
            "mirror_field": self.mirror_field_id.name or "",
        }
        if self.is_sync:
            entry["is_sync"] = True
        if self.search_field_name:
            entry["search_field_name"] = self.search_field_name
        if self.compute_field:
            entry["compute_field"] = self.compute_field
        return entry


class DevopsCgSyncBindDefault(models.Model):
    _name = "devops.cg.sync.bind.default"
    _description = "Code generator sync external binding - default field value"
    _order = "sequence, id"

    bind_id = fields.Many2one(
        comodel_name="devops.cg.sync.bind",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(default=10)
    key = fields.Char(
        required=True, help="Field name on the bound model to default"
    )
    value_type = fields.Selection(
        selection=[
            ("char", "Text"),
            ("bool", "Boolean"),
            ("int", "Integer"),
            ("float", "Float"),
        ],
        default="char",
        required=True,
    )
    value = fields.Char()

    def _coerce_value(self):
        self.ensure_one()
        raw = self.value or ""
        if self.value_type == "bool":
            return raw.strip().lower() in ("1", "true", "yes", "oui", "vrai")
        if self.value_type == "int":
            return int(raw) if raw.strip() else 0
        if self.value_type == "float":
            return float(raw) if raw.strip() else 0.0
        return raw
