# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models
from odoo.exceptions import ValidationError

PERMS = ("perm_read", "perm_write", "perm_create", "perm_unlink")


class ErplibreStudioAccess(models.Model):
    """One row of the access grid of a project: what a group may do on a
    model the project creates or on an existing model. Apply makes it an
    ir.model.access under the external id ``xml_name``."""

    _name = "erplibre.studio.access"
    _inherit = "erplibre.studio.line"
    _description = "ERPLibre studio access right"
    _order = "model, id"

    model = fields.Char(
        required=True,
        help="A model the project creates, or a model of the database.",
    )
    group_id = fields.Many2one(
        "res.groups",
        string="Group",
        required=True,
        ondelete="cascade",
        help="A group with an external id: the module refers to it.",
    )
    perm_read = fields.Boolean(string="Read")
    perm_write = fields.Boolean(string="Write")
    perm_create = fields.Boolean(string="Create")
    perm_unlink = fields.Boolean(string="Delete")
    xml_name = fields.Char(compute="_compute_xml_name", store=True, readonly=True)

    _sql_constraints = [
        (
            "model_group_uniq",
            "unique(project_id, model, group_id)",
            "A project has one access row per model and group.",
        ),
    ]

    @api.model
    def _server_fields(self):
        return super()._server_fields() | {"xml_name"}

    def _studio_xml_name(self):
        """The name of the external id of the row: « access_<model>_<group
        external id> », dots as underscores."""
        self.ensure_one()
        group = self.group_id.sudo().get_external_id().get(self.group_id.id)
        return f"access_{self._underscored(self.model)}_{self._underscored(group)}"

    @api.depends("model", "group_id")
    def _compute_xml_name(self):
        for line in self:
            line.xml_name = line._studio_xml_name()

    @api.constrains("model", "group_id", *PERMS)
    def _check_studio_access_line(self):
        for line in self:
            line.project_id._studio_check_rights_model(line.model)
            line.project_id._studio_check_group(line.group_id)
            line.project_id._studio_check_access_line(line)
            if not any(line[perm] for perm in PERMS):
                raise ValidationError(
                    self.env._(
                        "An access row on %(model)s gives at least one right.",
                        model=line.model,
                    )
                )

    def _snapshot(self):
        return [
            {
                "model": line.model,
                "group_id": line.group_id.id,
                **{perm: line[perm] for perm in PERMS},
            }
            for line in self.sorted(lambda a: (a.model, a.group_id.id))
        ]

    @api.model
    def _studio_line_vals(self, item):
        return {
            "model": item.get("model"),
            "group_id": item.get("group_id"),
            **{perm: bool(item.get(perm)) for perm in PERMS},
        }
