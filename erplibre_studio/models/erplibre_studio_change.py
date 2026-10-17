# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import json

from lxml import etree
from odoo import api, fields, models

from .. import arch as studio_arch
from .erplibre_studio_project import NO_TOUCH_KEY

CHANGE_TYPES = [
    ("add_field", "Add a new field"),
    ("add_existing_field", "Add an existing field"),
    ("move", "Move"),
    ("hide", "Hide or show"),
    ("relabel", "Relabel"),
    ("required", "Required"),
    ("readonly", "Read-only"),
    ("help", "Tooltip"),
    ("optional", "Optional column"),
]


class ErplibreStudioChange(models.Model):
    """One change of a studio project: one inheritance spec on the
    combined arch of a view. The changes of a view apply in their
    sequence; ``xpath`` locates the node in the arch left by the earlier
    ones."""

    _name = "erplibre.studio.change"
    _description = "ERPLibre studio change"
    _order = "sequence, id"

    project_id = fields.Many2one(
        "erplibre.studio.project",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10, index=True)
    change_type = fields.Selection(CHANGE_TYPES, string="Type", required=True)
    model = fields.Char(required=True)
    view_id = fields.Many2one(
        "ir.ui.view",
        string="View",
        required=True,
        ondelete="cascade",
        help="The primary view the change inherits.",
    )
    view_type = fields.Selection([("form", "Form"), ("list", "List")], required=True)
    xpath = fields.Char(string="Node path", required=True)
    position = fields.Selection(
        [
            ("before", "Before"),
            ("after", "After"),
            ("inside", "Inside"),
            ("attributes", "Attributes"),
        ],
        required=True,
        default="after",
    )
    payload = fields.Text(default="{}", help="The JSON parameters of the change.")
    field_name = fields.Char(
        compute="_compute_field_name",
        store=True,
        help="The field the change adds or moves, when it names one.",
    )
    summary = fields.Char(compute="_compute_summary")
    spec = fields.Text(string="Inheritance spec", compute="_compute_spec")

    # ── the draft of the project ────────────────────────────────────────

    def _touch_projects(self, projects):
        """A change written from outside the editor operations (a form, an
        RPC call) is a change of the draft all the same: new revision, new
        state of its project."""
        if not self.env.context.get(NO_TOUCH_KEY):
            projects.exists()._touch()

    @api.model_create_multi
    def create(self, vals_list):
        changes = super().create(vals_list)
        self._touch_projects(changes.project_id)
        return changes

    def write(self, vals):
        projects = self.project_id
        res = super().write(vals)
        self._touch_projects(projects | self.project_id)
        return res

    def unlink(self):
        projects = self.project_id
        res = super().unlink()
        self._touch_projects(projects)
        return res

    @api.depends("payload")
    def _compute_field_name(self):
        for change in self:
            change.field_name = change._payload().get("field_name") or False

    def _payload(self):
        self.ensure_one()
        try:
            value = json.loads(self.payload or "{}")
        except ValueError:
            return {}
        return value if isinstance(value, dict) else {}

    def _set_payload(self, payload):
        self.payload = json.dumps(payload, sort_keys=True)

    def _as_dict(self):
        """The plain form of the change for ``arch.change_spec``."""
        self.ensure_one()
        return {
            "key": self.id,
            "type": self.change_type,
            "xpath": self.xpath,
            "position": self.position,
            "payload": self._payload(),
        }

    def _snapshot(self):
        """The fields that define the change, to compare two states of a
        project."""
        return [
            {
                "type": c.change_type,
                "model": c.model,
                "view_id": c.view_id.id,
                "view_type": c.view_type,
                "xpath": c.xpath,
                "position": c.position,
                "payload": c._payload(),
            }
            for c in self.sorted(lambda c: (c.sequence, c.id))
        ]

    @api.depends("change_type", "xpath", "position", "payload", "view_type")
    def _compute_spec(self):
        for change in self:
            try:
                spec = studio_arch.change_spec(change._as_dict(), change.view_type)
                change.spec = etree.tostring(
                    spec, encoding="unicode", pretty_print=True
                )
            except studio_arch.ArchError as exc:
                change.spec = change.project_id._arch_message(exc)
            except KeyError as exc:
                change.spec = str(exc)

    @api.depends("change_type", "xpath", "payload")
    def _compute_summary(self):
        labels = dict(self._fields["change_type"]._description_selection(self.env))
        for change in self:
            payload = change._payload()
            target = payload.get("field_name") or change.xpath
            value = payload.get("value")
            text = f"{labels.get(change.change_type)}: {target}"
            if change.change_type == "move":
                text = f"{labels.get('move')}: {payload.get('source')} → {change.xpath}"
            elif value not in (None, ""):
                text += f" = {value}"
            change.summary = text
