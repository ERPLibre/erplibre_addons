# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .erplibre_studio_access import PERMS
from .erplibre_studio_project import RULE_XML_NAME


class ErplibreStudioRule(models.Model):
    """A record rule of a project, on a model the project creates or on an
    existing model. Apply makes it an ir.rule under the external id
    ``xml_name``, set once at creation so that it stays the same through
    Apply, Discard and the generations."""

    _name = "erplibre.studio.rule"
    _inherit = "erplibre.studio.line"
    _description = "ERPLibre studio record rule"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    name = fields.Char(required=True)
    model = fields.Char(
        required=True,
        help="A model the project creates, or a model of the database.",
    )
    domain_force = fields.Text(
        string="Domain",
        required=True,
        default="[]",
        help="The records the rule lets the groups reach; it may name "
        "user, company_id, company_ids and time.",
    )
    group_ids = fields.Many2many(
        "res.groups",
        "erplibre_studio_rule_group_rel",
        "rule_id",
        "group_id",
        string="Groups",
        help="Empty: a global rule, for every user.",
    )
    perm_read = fields.Boolean(string="Read", default=True)
    perm_write = fields.Boolean(string="Write", default=True)
    perm_create = fields.Boolean(string="Create", default=True)
    perm_unlink = fields.Boolean(string="Delete", default=True)
    xml_name = fields.Char(readonly=True, copy=False)

    _sql_constraints = [
        (
            "xml_name_uniq",
            "unique(project_id, xml_name)",
            "Two rules of a project have the same external id.",
        ),
    ]

    def _free_xml_name(self, project, model, taken):
        """``rule_<model>_<n>``, ``n`` the first integer free in ``taken``
        (the names of the rules of ``project``); ``taken`` gets it."""
        base = f"rule_{self._underscored(model)}"
        count = 1
        while f"{base}_{count}" in taken:
            count += 1
        taken.add(f"{base}_{count}")
        return f"{base}_{count}"

    @api.model
    def _server_fields(self):
        return super()._server_fields() | {"xml_name"}

    @api.model_create_multi
    def create(self, vals_list):
        """The external id name comes from the server: a free one, or the
        one Discard restores."""
        vals_list = [self._drop_server_fields(vals) for vals in vals_list]
        taken = {}
        for vals in vals_list:
            if vals.get("xml_name"):
                continue
            project = self.env["erplibre.studio.project"].browse(vals["project_id"])
            names = taken.setdefault(
                project.id, set(project.rule_line_ids.mapped("xml_name"))
            )
            vals["xml_name"] = self._free_xml_name(project, vals.get("model"), names)
        rules = super(ErplibreStudioRule, self._server_writing()).create(vals_list)
        return rules.with_env(self.env)

    def write(self, vals):
        """A rule moved to another model gets the external id of a new rule:
        Apply removes the ir.rule of the former one."""
        vals = self._drop_server_fields(vals)
        moved = self.filtered(lambda r: "model" in vals and r.model != vals["model"])
        res = super().write(vals)
        for rule in moved:
            names = set((rule.project_id.rule_line_ids - rule).mapped("xml_name"))
            name = self._free_xml_name(rule.project_id, rule.model, names)
            super(ErplibreStudioRule, rule._server_writing()).write({"xml_name": name})
        return res

    def _check_studio_xml_name(self):
        """Raise ValidationError unless the external id name of the rule is
        « rule_ » then lower case letters, digits and underscores: it goes
        into the files of a generated module."""
        for rule in self:
            if not RULE_XML_NAME.match(rule.xml_name or ""):
                raise ValidationError(
                    self.env._(
                        "%(name)s is not a valid external id for a rule.",
                        name=rule.xml_name,
                    )
                )

    @api.constrains("model", "domain_force", "group_ids", "xml_name", *PERMS)
    def _check_studio_rule_line(self):
        self._check_studio_xml_name()
        for rule in self:
            project = rule.project_id
            project._studio_check_rights_model(rule.model)
            for group in rule.group_ids:
                project._studio_check_group(group)
            project._studio_check_rule(rule)

    def _snapshot(self):
        return [
            {
                "name": rule.name,
                "model": rule.model,
                "domain_force": rule.domain_force,
                "group_ids": sorted(rule.group_ids.ids),
                "xml_name": rule.xml_name,
                "sequence": rule.sequence,
                **{perm: rule[perm] for perm in PERMS},
            }
            for rule in self.sorted(lambda r: r.xml_name or "")
        ]

    @api.model
    def _studio_line_vals(self, item):
        return {
            "name": item.get("name"),
            "model": item.get("model"),
            "domain_force": item.get("domain_force") or "[]",
            "group_ids": [(6, 0, item.get("group_ids") or [])],
            "xml_name": item.get("xml_name"),
            "sequence": item.get("sequence") or 10,
            **{perm: bool(item.get(perm)) for perm in PERMS},
        }
