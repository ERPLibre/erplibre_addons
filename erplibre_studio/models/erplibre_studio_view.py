# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .erplibre_studio_change import VIEW_TYPES
from .erplibre_studio_project import NO_TOUCH_KEY


class ErplibreStudioView(models.Model):
    """A view the project adds to an existing model that has none of its
    type: Apply creates it as a primary view under the external id
    ``_studio_xml_name``, the default view of the model for that type. Its
    arch is recorded once, when the line is made, so that the node paths of
    its changes stay valid whatever the model gains since; the changes of
    the editor on it stay changes, bound to the line until Apply creates the
    view, then to the view."""

    _name = "erplibre.studio.view"
    _inherit = "erplibre.studio.line"
    _description = "ERPLibre studio view"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    model = fields.Char(required=True)
    view_type = fields.Selection(VIEW_TYPES, required=True)
    arch = fields.Text(
        readonly=True,
        help="The arch Apply gives the view, recorded when the line is made.",
    )
    applied = fields.Boolean(compute="_compute_applied")
    view_id = fields.Many2one(
        "ir.ui.view", compute="_compute_applied", string="View in the database"
    )
    layer_ids = fields.One2many(
        "erplibre.studio.geo.layer",
        "view_line_id",
        string="Layers",
        help="The layers of a GeoEngine view, written to base_geoengine by Apply.",
    )

    _sql_constraints = [
        (
            "model_view_type_uniq",
            "unique(model, view_type)",
            "Another studio project adds a view of this type to this model.",
        ),
    ]

    @api.model
    def _server_fields(self):
        return super()._server_fields() | {"arch"}

    # ── external id ─────────────────────────────────────────────────────

    def _studio_xml_name(self):
        """The name, under the module of the project, of the external id of
        the view Apply creates: « <model>_view_<type> », the model with its
        dots as underscores."""
        self.ensure_one()
        return f"{self._underscored(self.model)}_view_{self.view_type}"

    def _studio_view_name(self):
        """The ``name`` of the view Apply creates."""
        self.ensure_one()
        return f"{self.model}.{self.view_type}.studio"

    @api.depends("model", "view_type")
    def _compute_display_name(self):
        for line in self:
            line.display_name = f"{line.model}.{line.view_type}"

    @api.depends("model", "view_type", "project_id.module_name")
    def _compute_applied(self):
        for line in self:
            record = line.project_id._studio_record(
                "ir.ui.view", line._studio_xml_name()
            )
            line.view_id = record
            line.applied = bool(record)

    def _snapshot(self):
        """The view lines as the snapshot of the project keeps them; the
        key « layers » shows only for a line with layers, so that the
        snapshot of a line without them keeps the form it had before."""
        items = []
        for line in self.sorted(lambda v: (v.sequence, v.model, v.view_type)):
            item = {
                "model": line.model,
                "view_type": line.view_type,
                "arch": line.arch or "",
                "sequence": line.sequence,
            }
            if line.layer_ids:
                item["layers"] = line.layer_ids._snapshot()
            items.append(item)
        return items

    @api.model
    def _studio_line_vals(self, item, project):
        """The values of a line from ``item``, one entry of ``_snapshot``,
        its layers included."""
        vals = {
            key: item.get(key) for key in ("model", "view_type", "arch", "sequence")
        }
        layers = item.get("layers") or []
        if layers:
            vals["layer_ids"] = [
                (0, 0, dict(layer, project_id=project.id)) for layer in layers
            ]
        return vals

    # ── constraints ─────────────────────────────────────────────────────

    @api.constrains("model", "view_type")
    def _check_studio_view(self):
        for line in self:
            if line.model not in self.env:
                raise ValidationError(
                    self.env._("Unknown model %(model)s.", model=line.model)
                )

    # ── writes ──────────────────────────────────────────────────────────

    def write(self, vals):
        """A view keeps its model and its type: its changes locate their
        nodes in its arch."""
        for line in self:
            for key in ("model", "view_type"):
                if key in vals and vals[key] != line[key]:
                    raise ValidationError(
                        self.env._(
                            "A view added by a project keeps its model and its type."
                        )
                    )
        return super().write(vals)

    def unlink(self):
        """A view leaves the project with its changes, before and after
        Apply, the changes of the project that show the new fields they
        define, and the changes that depend on the nodes these add."""
        for line in self:
            project = line.project_id
            record = line.view_id
            own = project.change_ids.filtered(
                lambda c, line=line, record=record: c.view_line_id == line
                or (record and c.view_id == record)
            )
            if not own:
                continue
            project._studio_check_inverse_removal(own)
            names = {}
            for change in own.filtered(lambda c: c.change_type == "add_field"):
                names.setdefault(change.model, set()).add(change.field_name)
            leaving = project._studio_inverse_dependents(
                own | project._studio_changes_of_fields(names)
            )
            leaving.with_context(**{NO_TOUCH_KEY: True}).unlink()
        return super().unlink()
