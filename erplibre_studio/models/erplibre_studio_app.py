# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from .. import arch as studio_arch
from .erplibre_studio_project import APP_XML_NAME


class ErplibreStudioApp(models.Model):
    """An app of the project: a top-level menu, its icon, and the category
    of its groups. Apply makes the menu under the external id ``xml_name``,
    set once at creation so that it stays the same through Apply, Discard
    and the generations."""

    _name = "erplibre.studio.app"
    _inherit = "erplibre.studio.line"
    _description = "ERPLibre studio app"
    _order = "sequence, id"

    sequence = fields.Integer(
        default=10,
        help="The order of the apps in the project: the first one gives the "
        "icon of the generated module.",
    )
    name = fields.Char(
        required=True,
        help="The label of the menu, and of the " "category of the groups of the app.",
    )
    icon = fields.Char(
        help="« <module>,static/description/icon.png », the icon of an "
        "installed module; empty: the icon of the studio.",
    )
    menu_sequence = fields.Integer(default=50)
    xml_name = fields.Char(readonly=True, copy=False)
    model_line_ids = fields.One2many("erplibre.studio.model", "app_id", string="Models")
    group_line_ids = fields.One2many("erplibre.studio.group", "app_id", string="Groups")
    applied = fields.Boolean(compute="_compute_applied")

    _sql_constraints = [
        (
            "xml_name_uniq",
            "unique(project_id, xml_name)",
            "Two apps of a project have the same external id.",
        ),
    ]

    @api.model
    def _server_fields(self):
        return super()._server_fields() | {"xml_name"}

    def _studio_xml_names(self):
        """The names, under the module of the project, of what the app makes:
        ``menu`` (its top-level menu), ``category`` (the category of its
        groups), and ``icon_path``, its icon in the generated module."""
        self.ensure_one()
        return {
            "menu": self.xml_name,
            "category": f"module_category_{self.xml_name[len('menu_'):]}",
            "icon_path": f"static/description/{self.xml_name}.png",
        }

    @api.depends("xml_name", "project_id.module_name")
    def _compute_applied(self):
        """Whether Apply made the menu or the category of the app."""
        for app in self:
            names = app._studio_xml_names() if app.xml_name else {}
            project = app.project_id
            app.applied = bool(
                names
                and (
                    project._studio_record("ir.ui.menu", names["menu"])
                    or project._studio_record("ir.module.category", names["category"])
                )
            )

    @api.model
    def _free_xml_name(self, name, taken):
        """« menu_app » when free in ``taken`` (the names of the apps of the
        project), else « menu_app_<slug of name> » with a free suffix;
        ``taken`` gets it."""
        if "menu_app" not in taken:
            result = "menu_app"
        else:
            base = f"menu_app_{studio_arch.slug(name, 'app')}"
            result, count = base, 2
            while result in taken:
                result = f"{base}_{count}"
                count += 1
        taken.add(result)
        return result

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self._drop_server_fields(vals) for vals in vals_list]
        taken = {}
        for vals in vals_list:
            if vals.get("xml_name"):
                continue
            project = self.env["erplibre.studio.project"].browse(vals["project_id"])
            names = taken.setdefault(
                project.id, set(project.app_ids.mapped("xml_name"))
            )
            vals["xml_name"] = self._free_xml_name(vals.get("name") or "", names)
        apps = super(ErplibreStudioApp, self._server_writing()).create(vals_list)
        return apps.with_env(self.env)

    def unlink(self):
        """Refused while a model or a group of the project goes in the app."""
        for app in self:
            users = app.model_line_ids.mapped("model") + app.group_line_ids.mapped(
                "name"
            )
            if users:
                raise UserError(
                    self.env._(
                        "The app %(app)s cannot be removed: %(items)s go in it.",
                        app=app.name,
                        items=", ".join(users),
                    )
                )
        return super().unlink()

    @api.constrains("name", "icon", "xml_name")
    def _check_studio_app(self):
        for app in self:
            label = (app.name or "").strip()
            if not label:
                raise ValidationError(self.env._("An app needs a name."))
            app.project_id._check_field_texts(label, "")
            if app.icon:
                app.project_id._studio_icon_module(app.icon)
            if not APP_XML_NAME.match(app.xml_name or ""):
                raise ValidationError(
                    self.env._(
                        "%(name)s is not a valid external id for an app.",
                        name=app.xml_name,
                    )
                )

    def _studio_menu_models(self):
        """The model lines whose menu goes in the app: Apply makes the menu of
        the app for them only."""
        self.ensure_one()
        return self.model_line_ids.filtered(lambda m: m.menu_mode == "app")

    def _studio_chain(self):
        """Whether the groups of the app are totally ordered by what they
        imply: the user form then shows them as one selection; otherwise, as
        checkboxes in developer mode only (``res.users``)."""
        self.ensure_one()
        groups = self.group_line_ids
        order = {
            group: len(group._studio_trans_implied_lines() & groups) for group in groups
        }
        return len(set(order.values())) == len(groups)

    def _snapshot(self):
        return [
            {
                "xml_name": app.xml_name,
                "name": app.name,
                "icon": app.icon or "",
                "menu_sequence": app.menu_sequence,
                "sequence": app.sequence,
            }
            for app in self.sorted(lambda a: a.xml_name or "")
        ]

    @api.model
    def _studio_line_vals(self, item, project):
        return {
            "xml_name": item.get("xml_name"),
            "name": item.get("name"),
            "icon": item.get("icon") or False,
            "menu_sequence": item.get("menu_sequence") or 0,
            "sequence": item.get("sequence") or 10,
        }
