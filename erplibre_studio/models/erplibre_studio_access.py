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
        ondelete="cascade",
        help="A group with an external id: the module refers to it.",
    )
    group_line_id = fields.Many2one(
        "erplibre.studio.group",
        string="Group of the project",
        ondelete="cascade",
        help="A group the project creates, instead of an existing group.",
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
        external id> », dots as underscores; for a group of the project,
        « access_<model>_<name of its external id> », without the module, so
        that it stays the same when the module is renamed."""
        self.ensure_one()
        if self.group_line_id:
            group = self.group_line_id.xml_name
        else:
            group = self.group_id.sudo().get_external_id().get(self.group_id.id)
        return f"access_{self._underscored(self.model)}_{self._underscored(group)}"

    @api.depends("model", "group_id", "group_line_id.xml_name")
    def _compute_xml_name(self):
        for line in self:
            line.xml_name = line._studio_xml_name()

    @api.constrains("model", "group_id", "group_line_id", *PERMS)
    def _check_studio_access_line(self):
        for line in self:
            if bool(line.group_id) == bool(line.group_line_id):
                raise ValidationError(
                    self.env._(
                        "An access row on %(model)s names one group: an existing "
                        "group or a group of the project.",
                        model=line.model,
                    )
                )
            line.project_id._studio_check_rights_model(line.model)
            if line.group_id:
                line.project_id._studio_check_group(line.group_id)
            elif line.group_line_id.project_id != line.project_id:
                raise ValidationError(
                    self.env._(
                        "The access row on %(model)s names a group of another "
                        "project.",
                        model=line.model,
                    )
                )
            else:
                twin = line.project_id.access_line_ids.filtered(
                    lambda a, line=line: a != line
                    and a.model == line.model
                    and a.group_line_id == line.group_line_id
                )
                if twin:
                    raise ValidationError(
                        self.env._("A project has one access row per model and group.")
                    )
            line.project_id._studio_check_access_line(line)
            if not any(line[perm] for perm in PERMS):
                raise ValidationError(
                    self.env._(
                        "An access row on %(model)s gives at least one right.",
                        model=line.model,
                    )
                )

    def _snapshot(self):
        items = []
        for line in self.sorted(
            lambda a: (a.model, a.group_id.id, a.group_line_id.xml_name or "")
        ):
            item = {
                "model": line.model,
                "group_id": line.group_id.id,
                **{perm: line[perm] for perm in PERMS},
            }
            if line.group_line_id:
                item["group_line"] = line.group_line_id.xml_name
            items.append(item)
        return items

    @api.model
    def _studio_line_vals(self, item, project):
        """The values of a row from ``item``; a group of the project is
        found by its external id name."""
        group_line = project.group_line_ids.filtered(
            lambda g: item.get("group_line") and g.xml_name == item["group_line"]
        )
        return {
            "model": item.get("model"),
            "group_id": item.get("group_id") or False,
            "group_line_id": group_line[:1].id,
            **{perm: bool(item.get(perm)) for perm in PERMS},
        }
