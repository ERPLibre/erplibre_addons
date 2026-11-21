# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import json

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .. import arch as studio_arch
from .erplibre_studio_project import ADMIN_GROUPS, GROUP_XML_NAME


class ErplibreStudioGroup(models.Model):
    """A group the project creates, in the category of its app. Apply makes
    it a res.groups under the external id ``xml_name``, set once at
    creation, so that the users keep it through Apply, Discard and the
    generations. It implies groups of the project and existing groups; the
    users get it in the user form, as any group."""

    _name = "erplibre.studio.group"
    _inherit = "erplibre.studio.line"
    _description = "ERPLibre studio group"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    app_id = fields.Many2one(
        "erplibre.studio.app",
        string="App",
        required=True,
        ondelete="cascade",
        help="The app whose category holds the group.",
    )
    name = fields.Char(required=True)
    comment = fields.Text()
    implied_line_ids = fields.Many2many(
        "erplibre.studio.group",
        "erplibre_studio_group_implied_rel",
        "group_id",
        "implied_id",
        string="Implied groups of the project",
    )
    implied_group_ids = fields.Many2many(
        "res.groups",
        "erplibre_studio_group_res_implied_rel",
        "group_line_id",
        "group_id",
        string="Implied groups",
        help="Existing groups, with an external id, that the members of the "
        "group get with it.",
    )
    implied_refs = fields.Text(
        readonly=True,
        copy=False,
        help="The external ids of the implied existing groups, as last chosen.",
    )
    missing_implied = fields.Char(
        compute="_compute_missing_implied",
        help="The implied groups that left the database since they were chosen.",
    )
    xml_name = fields.Char(readonly=True, copy=False)
    applied = fields.Boolean(compute="_compute_applied")

    _sql_constraints = [
        (
            "xml_name_uniq",
            "unique(project_id, xml_name)",
            "Two groups of a project have the same external id.",
        ),
    ]

    @api.model
    def _server_fields(self):
        return super()._server_fields() | {"xml_name", "implied_refs"}

    # ── external ids ────────────────────────────────────────────────────

    def _studio_full_xmlid(self):
        self.ensure_one()
        return f"{self.project_id.module_name}.{self.xml_name}"

    def _studio_group_record(self):
        """The res.groups Apply made for the group, in sudo, or an empty
        recordset."""
        if len(self) != 1:
            return self.env["res.groups"].sudo()
        return self.project_id._studio_record("res.groups", self.xml_name)

    @api.depends("xml_name", "project_id.module_name")
    def _compute_applied(self):
        for group in self:
            group.applied = bool(group._studio_group_record())

    @api.model
    def _free_xml_name(self, app, name, taken):
        """« group_<app name>_<group name> », with a free suffix in ``taken``
        (the names of the groups of the project); ``taken`` gets it."""
        base = (
            f"group_{studio_arch.slug(app.name, 'app')}_"
            f"{studio_arch.slug(name, 'group')}"
        )
        result, count = base, 2
        while result in taken:
            result = f"{base}_{count}"
            count += 1
        taken.add(result)
        return result

    # ── implied groups ──────────────────────────────────────────────────

    def _studio_implied_refs(self):
        self.ensure_one()
        xmlids = self.implied_group_ids.sudo().get_external_id()
        return json.dumps(sorted(x for x in xmlids.values() if x))

    def _write_implied_refs(self):
        for group in self:
            refs = group._studio_implied_refs()
            if group.implied_refs != refs:
                super(ErplibreStudioGroup, group._server_writing()).write(
                    {"implied_refs": refs}
                )

    def _studio_missing_implied_refs(self):
        """The external ids of ``implied_refs`` that no implied group of the
        line has any longer."""
        self.ensure_one()
        try:
            refs = json.loads(self.implied_refs or "[]")
        except ValueError:
            return []
        present = set(self.implied_group_ids.sudo().get_external_id().values())
        return [ref for ref in refs if ref not in present]

    @api.depends("implied_refs", "implied_group_ids")
    def _compute_missing_implied(self):
        for group in self:
            group.missing_implied = ", ".join(group._studio_missing_implied_refs())

    def _studio_implied_closure(self):
        """The groups of the project ``self`` implies, directly or not;
        ``self`` is among them only on a cycle."""
        result = self.browse()
        todo = self.implied_line_ids
        while todo:
            result |= todo
            todo = todo.implied_line_ids - result
        return result

    def _studio_trans_implied_lines(self):
        """The groups of the project ``self`` implies, directly or not."""
        self.ensure_one()
        return self._studio_implied_closure() - self

    # ── writes ──────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self._drop_server_fields(vals) for vals in vals_list]
        taken = {}
        for vals in vals_list:
            if vals.get("xml_name"):
                continue
            project = self.env["erplibre.studio.project"].browse(vals["project_id"])
            app = self.env["erplibre.studio.app"].browse(vals.get("app_id"))
            names = taken.setdefault(
                project.id, set(project.group_line_ids.mapped("xml_name"))
            )
            vals["xml_name"] = self._free_xml_name(app, vals.get("name") or "", names)
        groups = super(ErplibreStudioGroup, self._server_writing()).create(vals_list)
        for group, vals in zip(groups, vals_list):
            if "implied_refs" not in vals:
                group._write_implied_refs()
        return groups.with_env(self.env)

    def write(self, vals):
        vals = self._drop_server_fields(vals)
        res = super().write(vals)
        if "implied_group_ids" in vals and "implied_refs" not in vals:
            self._write_implied_refs()
        return res

    # ── constraints ─────────────────────────────────────────────────────

    @api.constrains(
        "name", "comment", "app_id", "implied_line_ids", "implied_group_ids"
    )
    def _check_studio_group(self):
        """A name, an app of the project, groups of the same project, no
        cycle; existing groups with an external id, neither for users outside
        the company nor granting the Settings."""
        for group in self:
            project = group.project_id
            label = (group.name or "").strip()
            if not label:
                raise ValidationError(self.env._("A group needs a name."))
            project._check_field_texts(label, group.comment or "")
            twin = group.app_id.group_line_ids.filtered(
                lambda g, group=group: g != group and (g.name or "").strip() == label
            )
            if twin:
                raise ValidationError(
                    self.env._(
                        "The app %(app)s has a group %(name)s already.",
                        app=group.app_id.name,
                        name=label,
                    )
                )
            if group.app_id.project_id != project:
                raise ValidationError(
                    self.env._(
                        "The group %(name)s goes in an app of its project.",
                        name=label,
                    )
                )
            if group.implied_line_ids - project.group_line_ids:
                raise ValidationError(
                    self.env._(
                        "The group %(name)s implies a group of another project.",
                        name=label,
                    )
                )
            if not GROUP_XML_NAME.match(group.xml_name or ""):
                raise ValidationError(
                    self.env._(
                        "%(name)s is not a valid external id for a group.",
                        name=group.xml_name,
                    )
                )
            admins = self.env["res.groups"].sudo()
            for xmlid in ADMIN_GROUPS:
                admins |= self.env.ref(xmlid, raise_if_not_found=False) or admins
            for implied in group.implied_group_ids.sudo():
                project._studio_check_group(implied)
                if implied in admins or project._studio_share_groups(implied):
                    raise ValidationError(
                        self.env._(
                            "A project group cannot imply %(group)s.",
                            group=implied.full_name,
                        )
                    )
                # A group that implies the Settings, directly or not, would
                # grant them to the members of the project group as well.
                granted = implied.trans_implied_ids & admins
                if granted:
                    raise ValidationError(
                        self.env._(
                            "A project group cannot imply %(group)s: it grants "
                            "%(admin)s.",
                            group=implied.full_name,
                            admin=", ".join(granted.mapped("full_name")),
                        )
                    )
        lines = self.mapped("project_id.group_line_ids")
        cycle = lines.filtered(lambda g: g in g._studio_implied_closure())
        if cycle:
            raise ValidationError(
                self.env._(
                    "The groups %(groups)s imply each other.",
                    groups=", ".join(cycle.mapped("name")),
                )
            )

    # ── snapshot ────────────────────────────────────────────────────────

    def _snapshot(self):
        return [
            {
                "xml_name": group.xml_name,
                "app": group.app_id.xml_name,
                "name": group.name,
                "comment": group.comment or "",
                "implied_lines": sorted(group.implied_line_ids.mapped("xml_name")),
                "implied_group_ids": sorted(group.implied_group_ids.ids),
                "implied_refs": group.implied_refs or "[]",
                "sequence": group.sequence,
            }
            for group in self.sorted(lambda g: g.xml_name or "")
        ]

    @api.model
    def _studio_line_vals(self, item, project):
        """The values of a group from ``item``, without the groups of the
        project it implies: ``_studio_restore_implied`` sets them once every
        group is back."""
        app = project.app_ids.filtered(lambda a: a.xml_name == item.get("app"))
        vals = {
            "xml_name": item.get("xml_name"),
            "app_id": app[:1].id,
            "name": item.get("name"),
            "comment": item.get("comment") or False,
            "implied_group_ids": [(6, 0, item.get("implied_group_ids") or [])],
            "sequence": item.get("sequence") or 10,
        }
        if item.get("implied_refs"):
            vals["implied_refs"] = item["implied_refs"]
        return vals

    @api.model
    def _studio_restore_implied(self, project, item):
        """Give the group of ``item`` back the groups of ``project`` it
        implied, those that are back."""
        group = project.group_line_ids.filtered(
            lambda g: g.xml_name == item.get("xml_name")
        )
        implied = project.group_line_ids.filtered(
            lambda g: g.xml_name in (item.get("implied_lines") or [])
        )
        if group and implied:
            group.write({"implied_line_ids": [(6, 0, implied.ids)]})
