# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import ast
import inspect
import json
import logging
import re

import psycopg2
from lxml import etree
from odoo import Command, api, fields, models
from odoo.addons.base.models.ir_module import STATES
from odoo.exceptions import UserError, ValidationError
from odoo.modules.module import get_module_path
from odoo.osv import expression
from odoo.tools import sql
from odoo.tools.misc import file_path
from odoo.tools.safe_eval import safe_eval

from .. import arch as studio_arch
from .studio_pending import added_view, is_added_view, is_pending_view, pending_view

_logger = logging.getLogger(__name__)

# The context key that asks get_views for the draft of a project. The web
# client sends get_views only the « lang » and « *_view_ref » keys of the
# context, and Odoo keys its view cache on them: the suffix is what lets
# the key through. Value: « <project id>:<draft revision> ».
PREVIEW_KEY = "erplibre_studio_view_ref"
# The views of the project left out of a combined arch: the draft replaces
# them. Its value must be a ``ViewExclusion``.
EXCLUDE_KEY = "erplibre_studio_exclude_view_ids"
# Set by the project on its own writes of the fields it manages, together
# with sudo: an RPC call cannot be superuser.
INTERNAL_KEY = "erplibre_studio_internal"
# Set by the project when it changes its changes itself and touches its
# draft once for all of them.
NO_TOUCH_KEY = "erplibre_studio_no_touch"

# The fields of a project only its own methods write; ``_managed_fields``
# adds those of the modules that extend the project.
MANAGED_FIELDS = frozenset(
    {
        "state",
        "draft_revision",
        "applied_snapshot",
        "applied_date",
        "field_ids",
        "studio_view_ids",
        "created_model_ids",
        "created_view_ids",
        "created_action_ids",
        "created_menu_ids",
        "created_access_ids",
        "created_rule_ids",
        "created_category_ids",
        "created_group_ids",
        "approved_snapshot",
        "approved_uid",
        "approved_date",
    }
)

# What Apply creates for the lines of a project, by kind: the managed field
# that holds the records. ``_studio_remove_created`` removes them in the
# order of REMOVAL_ORDER, so that nothing removed is still referred to.
CREATED_FIELDS = {
    "models": "created_model_ids",
    "primary_views": "created_view_ids",
    "actions": "created_action_ids",
    "menus": "created_menu_ids",
    "access": "created_access_ids",
    "rules": "created_rule_ids",
    "groups": "created_group_ids",
    "categories": "created_category_ids",
}
# What Apply writes for the layers of the GeoEngine views the project adds,
# by kind of REMOVAL_ORDER: the model of base_geoengine, which exists once it
# is installed. The layers are found by their external ids under the module
# (``_studio_geo_layer_records``), the studio does not depend on it. A layer
# goes before its view, which it names with « ondelete restrict », and
# before the geo field it draws.
GEO_LAYER_KINDS = {
    "raster_layers": "geoengine.raster.layer",
    "vector_layers": "geoengine.vector.layer",
}
REMOVAL_ORDER = (
    "menus",
    "actions",
    "rules",
    "access",
    "raster_layers",
    "vector_layers",
    "views",
    "primary_views",
    "fields",
    "models",
    "groups",
    "categories",
)
# The models whose records Odoo deletes with the ir.model or ir.model.fields
# they name, that ``_studio_cascade_records`` leaves out: the reflection of
# the models and the fields, which goes with them; the access rights and the
# rules, which the removal checks on their own; the data attached to the
# records of the models, which go with their records.
CASCADE_SKIPPED = frozenset(
    {
        "ir.model",
        "ir.model.fields",
        "ir.model.fields.selection",
        "ir.model.constraint",
        "ir.model.relation",
        "ir.model.inherit",
        "ir.model.access",
        "ir.rule",
        "mail.activity",
        "mail.followers",
        "mail.message",
        "mail.tracking.value",
    }
)
# The file written into a generated module that names the project and the
# database it comes from (erplibre_studio_generate writes it).
MARKER_FILE = ".erplibre_studio"

# The priority of the default views of a model the studio creates: the
# one Odoo gives a view that names none.
MODEL_VIEW_PRIORITY = 16
# The icon of an app whose project chose none.
DEFAULT_APP_ICON = "erplibre_studio,static/description/icon.png"
# The icon of an app: the icon of an installed module.
_APP_ICON = re.compile(r"^([a-z][a-z0-9_]*),static/description/icon\.png$")
# The longest record rule domain the studio records.
RULE_DOMAIN_SIZE = 2000
PERMS = ("perm_read", "perm_write", "perm_create", "perm_unlink")
# The existing models a project gives no access row nor rule on, by the
# start of their name: the rights, the users, the companies, the settings
# and the technical records of the database (``ir.*``: views, actions,
# server actions, crons, external ids, modules, parameters), and the models
# of the ERPLibre modules, the studio's among them. A row on one of them
# would decide who changes the rights, or open the configuration of the
# server, in every database that installs the generated module.
PROTECTED_MODEL_PREFIXES = (
    "ir.",
    "erplibre.",
    "res.users",
    "res.groups",
    "res.company",
    "res.config",
    "res.device",
    "base.",
    "bus.",
    "auth_",
)
# The name of an external id Apply gives: letters, digits, « _ » and « - »;
# it goes as such into the files of a generated module.
XML_NAME = re.compile(r"^[A-Za-z0-9_\-]+$")
# The name of the external id of a rule line.
RULE_XML_NAME = re.compile(r"^rule_[a-z0-9_]+$")
# The name of the external id of the top-level menu of an app.
APP_XML_NAME = re.compile(r"^menu_app(_[a-z0-9_]+)?$")
# The name of the external id of a group of a project.
GROUP_XML_NAME = re.compile(r"^group_[a-z0-9_]+$")
# The existing groups a group of a project never implies: it would grant
# the Settings to its users.
ADMIN_GROUPS = ("base.group_system", "base.group_erp_manager")
# The rights a share group (portal, public) never gets from a project on a
# model the project does not create.
SHARE_DENIED_PERMS = ("perm_write", "perm_create", "perm_unlink")
# The fields of a project whose write changes its draft or what Apply made:
# the editor guard applies to them as to the lines.
GUARDED_FIELDS = frozenset(
    {
        "module_name",
        "change_ids",
        "new_model_ids",
        "access_line_ids",
        "rule_line_ids",
        "app_ids",
        "group_line_ids",
        "view_line_ids",
    }
)
# The values of a project without an approval of its real preview.
APPROVAL_CLEARED = {
    "approved_snapshot": False,
    "approved_uid": False,
    "approved_date": False,
}
# The states of a generated module that owns what its project applied.
MODULE_OWNING_STATES = ("installed", "to upgrade", "to remove")
# Set to SERVER_VALUES by the server code that writes the fields of the
# lines the server computes (the external id names, kept by Discard): a
# client value of these fields is dropped otherwise.
RESTORE_KEY = "erplibre_studio_restore"


class _ServerValues:
    """The value of RESTORE_KEY: a Python object, which no RPC call can
    put in its context."""


SERVER_VALUES = _ServerValues()


def check_studio_write(env):
    """Raise unless ``env`` may write the draft of a project outside the
    editor operations: the guard of the editor (Settings group and
    developer mode). Server code in sudo skips it: it passed that guard
    itself."""
    if not env.su:
        env["erplibre.studio.project"]._check_studio_access()


def protected_model(model):
    """Whether ``model`` takes no access row nor rule from a project (see
    PROTECTED_MODEL_PREFIXES)."""
    return (model or "").startswith(PROTECTED_MODEL_PREFIXES)


# The mixins a new model of a project inherits when its chatter is on.
CHATTER_MODELS = ("mail.thread", "mail.activity.mixin")


def delegation_classes(registry, model):
    """The classes of ``registry`` a field of ``model`` lands on: the class
    of ``model`` and those of the models that inherit it by delegation
    (``_inherits``, at any depth), which copy its fields as their own
    (``_add_inherited_fields``). A field there replaces a method or an
    attribute of that class of the same name. Empty for a model out of
    the registry. The classes and their children are known once built,
    before the setup of the models: the registry setup reads them too."""
    if model not in registry:
        return []
    return [registry[name] for name in registry.descendants([model], "_inherits")]


def attribute_names(cls):
    """The names of the methods and the attributes of ``cls``, its fields
    aside."""
    return {
        name
        for name in dir(cls)
        if not isinstance(inspect.getattr_static(cls, name, None), fields.Field)
    }


# Inheriting views apply by priority then id: 99 puts the studio view
# after the views of the modules, as in the draft.
STUDIO_PRIORITY = 99

NEW_FIELD_TYPES = (
    "char",
    "integer",
    "float",
    "boolean",
    "date",
    "datetime",
    "selection",
    "many2one",
    "text",
    "html",
    "monetary",
    "one2many",
    "many2many",
)
# The options of a new field set before Apply, and the types that take
# each one. A text or html column takes no index: a btree row holds about
# 2700 bytes, a longer value would be refused at write. A translatable
# column (jsonb) is indexed by Odoo only with a trigram index, so a field
# is not both translatable and indexed. The editor keeps the same lists
# (FIELD_OPTIONS of studio_utils.js).
FIELD_OPTIONS = {
    "translate": ("char", "text", "html"),
    "index": (
        "char",
        "integer",
        "float",
        "boolean",
        "date",
        "datetime",
        "selection",
        "many2one",
        "monetary",
    ),
    "size": ("char",),
}
# The largest maximum size of a char field.
MAX_FIELD_SIZE = 10000
# What a many2one does when its record is deleted.
ON_DELETE = ("set null", "cascade", "restrict")

# The editor operations on a view of a model not created yet: those that
# need no record nor field of the database (no filter, no group-by).
PENDING_VIEW_OPERATIONS = {
    "form": (
        "add_field",
        "add_existing_field",
        "add_group",
        "add_page",
        "add_separator",
        "move",
        "remove",
        "hide",
        "relabel",
        "required",
        "readonly",
        "help",
        "update_field",
        "rename_field",
        "set_attribute",
    ),
    "list": (
        "add_field",
        "add_existing_field",
        "move",
        "remove",
        "hide",
        "relabel",
        "optional",
        "update_field",
        "rename_field",
        "set_attribute",
    ),
    "search": ("add_existing_field", "move", "remove"),
}
# The checks of the technical name of a new field, in the order they run
# and the editor lists them.
FIELD_NAME_CHECKS = ("format", "reserved", "prefix", "unique")
# The checks of the technical name of a new model, in the order they apply.
MODEL_NAME_CHECKS = ("format", "reserved", "prefix", "unique")

# The attributes of a node that hold a text people read, not a field name.
HUMAN_ATTRIBUTES = ("string", "help", "title", "tooltip", "placeholder")

# The ir.model.fields values that fix the relation of a field: Apply never
# changes them on a field it created.
RELATION_VALUES = frozenset(
    {"relation", "relation_field", "relation_table", "column1", "column2"}
)

# The fields_get attributes the operations check.
FIELD_INFO = [
    "string",
    "type",
    "store",
    "groupable",
    "searchable",
    "sortable",
    "aggregator",
    "selection",
    "relation",
]


class ViewExclusion(tuple):
    """The ids of the views left out of a combined arch (``EXCLUDE_KEY``).
    A Python type that no RPC call can build: a list sent by a client in
    its context is ignored, so the shared view cache never holds an arch
    without the views of the modules."""


class ErplibreStudioProject(models.Model):
    """A studio project: the changes of views (form, list, kanban, search,
    pivot, graph, calendar, timeline, hierarchy, activity) that make one
    module. Its life: draft changes (previewed by its editor only), then
    applied to the database (``x_`` fields, one inherited view per edited
    view, under external ids of the module ``module_name``). Writing the
    project as a module is the part of erplibre_studio_generate."""

    _name = "erplibre.studio.project"
    _description = "ERPLibre studio project"
    _order = "write_date desc, id desc"

    name = fields.Char(required=True)
    module_name = fields.Char(
        string="Technical name",
        required=True,
        help="Name of the module the project makes: lower case letters, "
        "digits and underscores. The external ids of its views in the "
        "database start with it.",
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("applied", "Applied"),
        ],
        default="draft",
        required=True,
        readonly=True,
        copy=False,
    )
    user_id = fields.Many2one(
        "res.users",
        string="Editor",
        default=lambda self: self.env.user,
        help="The only user who sees the draft in the views.",
    )
    change_ids = fields.One2many(
        "erplibre.studio.change", "project_id", string="Changes", copy=False
    )
    change_count = fields.Integer(compute="_compute_change_count")
    field_ids = fields.Many2many(
        "ir.model.fields",
        "erplibre_studio_project_field_rel",
        "project_id",
        "field_id",
        string="Fields created",
        readonly=True,
        copy=False,
    )
    studio_view_ids = fields.Many2many(
        "ir.ui.view",
        "erplibre_studio_project_view_rel",
        "project_id",
        "view_id",
        string="Views created",
        readonly=True,
        copy=False,
    )
    draft_revision = fields.Integer(readonly=True, copy=False)
    applied_snapshot = fields.Text(readonly=True, copy=False)
    applied_date = fields.Datetime(readonly=True, copy=False)
    module_id = fields.Many2one(
        "ir.module.module", compute="_compute_module_id", string="Module"
    )
    module_state = fields.Selection(
        STATES, compute="_compute_module_id", string="Module state"
    )
    app_ids = fields.One2many(
        "erplibre.studio.app",
        "project_id",
        string="Apps",
        copy=False,
        help="The top-level menus of the project, where its models « In an "
        "app of the project » go, and the categories of its groups.",
    )
    group_line_ids = fields.One2many(
        "erplibre.studio.group", "project_id", string="Groups", copy=False
    )
    new_model_ids = fields.One2many(
        "erplibre.studio.model", "project_id", string="New models", copy=False
    )
    access_line_ids = fields.One2many(
        "erplibre.studio.access", "project_id", string="Access rights", copy=False
    )
    rule_line_ids = fields.One2many(
        "erplibre.studio.rule", "project_id", string="Record rules", copy=False
    )
    view_line_ids = fields.One2many(
        "erplibre.studio.view",
        "project_id",
        string="Views added",
        copy=False,
        help="The views the project adds to existing models that have none "
        "of their type.",
    )
    item_count = fields.Integer(compute="_compute_item_count")
    created_model_ids = fields.Many2many(
        "ir.model",
        "erplibre_studio_project_model_rel",
        "project_id",
        "model_id",
        string="Models created",
        readonly=True,
        copy=False,
    )
    created_view_ids = fields.Many2many(
        "ir.ui.view",
        "erplibre_studio_project_primary_view_rel",
        "project_id",
        "view_id",
        string="Default views created",
        readonly=True,
        copy=False,
    )
    created_action_ids = fields.Many2many(
        "ir.actions.act_window",
        "erplibre_studio_project_action_rel",
        "project_id",
        "action_id",
        string="Actions created",
        readonly=True,
        copy=False,
    )
    created_menu_ids = fields.Many2many(
        "ir.ui.menu",
        "erplibre_studio_project_menu_rel",
        "project_id",
        "menu_id",
        string="Menus created",
        readonly=True,
        copy=False,
    )
    created_access_ids = fields.Many2many(
        "ir.model.access",
        "erplibre_studio_project_access_rel",
        "project_id",
        "access_id",
        string="Access rights created",
        readonly=True,
        copy=False,
    )
    created_rule_ids = fields.Many2many(
        "ir.rule",
        "erplibre_studio_project_rule_rel",
        "project_id",
        "rule_id",
        string="Record rules created",
        readonly=True,
        copy=False,
    )
    created_group_ids = fields.Many2many(
        "res.groups",
        "erplibre_studio_project_group_rel",
        "project_id",
        "group_id",
        string="Groups created",
        readonly=True,
        copy=False,
    )
    created_category_ids = fields.Many2many(
        "ir.module.category",
        "erplibre_studio_project_category_rel",
        "project_id",
        "category_id",
        string="Categories created",
        readonly=True,
        copy=False,
    )
    approved_snapshot = fields.Text(readonly=True, copy=False)
    approved_uid = fields.Many2one(
        "res.users", string="Approved by", readonly=True, copy=False
    )
    approved_date = fields.Datetime(readonly=True, copy=False)
    approved = fields.Boolean(
        compute="_compute_approved",
        help="The models not created yet, as approved for a real preview: "
        "any change of them withdraws the approval.",
    )

    _sql_constraints = [
        (
            "module_name_uniq",
            "unique(module_name)",
            "Another studio project generates this module.",
        ),
    ]

    # ── fields ──────────────────────────────────────────────────────────

    @api.depends("change_ids")
    def _compute_change_count(self):
        for project in self:
            project.change_count = len(project.change_ids)

    @api.depends(
        "change_ids",
        "new_model_ids",
        "access_line_ids",
        "rule_line_ids",
        "app_ids",
        "group_line_ids",
        "view_line_ids",
    )
    def _compute_item_count(self):
        for project in self:
            project.item_count = (
                len(project.change_ids)
                + len(project.new_model_ids)
                + len(project.access_line_ids)
                + len(project.rule_line_ids)
                + len(project.app_ids)
                + len(project.group_line_ids)
                + len(project.view_line_ids)
            )

    @api.depends("approved_snapshot", "draft_revision")
    def _compute_approved(self):
        for project in self:
            project.approved = bool(
                project.approved_snapshot
                and project.approved_snapshot == project._studio_preview_snapshot()
            )

    @api.depends("module_name")
    def _compute_module_id(self):
        Module = self.env["ir.module.module"].sudo()
        for project in self:
            module = Module.search([("name", "=", project.module_name or "")], limit=1)
            project.module_id = module
            project.module_state = module.state or False

    # ── constraints ─────────────────────────────────────────────────────

    @api.constrains("module_name")
    def _check_module_name(self):
        for project in self:
            name = project.module_name
            if not studio_arch.valid_module_name(name):
                raise ValidationError(
                    self.env._(
                        "%(name)s is not a valid technical name: lower case "
                        "letters, digits and underscores, starting with a letter.",
                        name=name,
                    )
                )
            path = get_module_path(name, display_warning=False)
            own = bool(path) and project._is_own_directory(path)
            if path and not own:
                raise ValidationError(
                    self.env._(
                        "A module named %(name)s already exists in %(path)s.",
                        name=name,
                        path=path,
                    )
                )
            module = self.env["ir.module.module"].sudo().search([("name", "=", name)])
            if module and not own:
                raise ValidationError(
                    self.env._("A module named %(name)s is already known.", name=name)
                )

    def _is_own_directory(self, path):
        """Whether the module directory ``path`` was made from this
        project, so that its name does not collide with it. Without a
        generation, no directory is: erplibre_studio_generate recognises
        the ones it writes."""
        self.ensure_one()
        return False

    @api.model
    def _managed_fields(self):
        """The names of the fields of a project only its own methods
        write."""
        return MANAGED_FIELDS

    def _check_managed_fields(self, vals_list):
        """Refuse a write of ``_managed_fields`` that does not come from
        the project itself."""
        if self.env.su and self.env.context.get(INTERNAL_KEY):
            return
        names = sorted({n for vals in vals_list for n in vals} & self._managed_fields())
        if names:
            raise UserError(
                self.env._(
                    "These fields of a studio project are managed by the "
                    "studio: %(fields)s",
                    fields=", ".join(names),
                )
            )

    def _internal(self):
        """The project as its own methods write it: see INTERNAL_KEY."""
        return self.sudo().with_context(**{INTERNAL_KEY: True})

    @api.model_create_multi
    def create(self, vals_list):
        self._check_managed_fields(vals_list)
        return super().create(vals_list)

    def write(self, vals):
        self._check_managed_fields([vals])
        if GUARDED_FIELDS & set(vals):
            check_studio_write(self.env)
        if "module_name" in vals:
            for project in self:
                if project.module_name != vals["module_name"]:
                    project._rename_studio_xmlids(vals["module_name"])
        editors = {project: project.user_id for project in self}
        res = super().write(vals)
        for project, editor in editors.items():
            if project.user_id != editor:
                # The draft moves to another user: a new preview revision,
                # so that no view cached for the former editor is reused.
                project._internal().draft_revision += 1
        return res

    def unlink(self):
        check_studio_write(self.env)
        for project in self:
            created = [project[name] for name in CREATED_FIELDS.values()]
            if any([project.studio_view_ids, project.field_ids, *created]):
                raise UserError(
                    self.env._(
                        "Revert the project %(name)s before deleting it: what "
                        "it created is in the database.",
                        name=project.name,
                    )
                )
        return super().unlink()

    @api.model
    def _studio_applied(self):
        """The projects that have records in the database while their
        generated module is not installed."""
        return self.search([]).filtered(
            lambda p: p.module_state != "installed"
            and any(
                [p.studio_view_ids, p.field_ids]
                + [p[name] for name in CREATED_FIELDS.values()]
            )
        )

    # ── guards ──────────────────────────────────────────────────────────

    @api.model
    def _check_studio_access(self):
        """Settings group and developer mode, as the developer panel."""
        self.env["erplibre.developer"]._check_panel_access()

    # ── models, menus and rights of the project ─────────────────────────

    @api.model
    def _studio_geo_available(self):
        """Whether the geometry types of base_geoengine (GEO_TYPES) are
        field types of this database: ir.model.fields.ttype takes them once
        base_geoengine is installed. The studio does not depend on it. The
        selection of the registry answers, not the field classes, which a
        module imported by another database of the process declares too."""
        known = self.env["ir.model.fields"]._fields["ttype"].get_values(self.env)
        return "geo_point" in known

    @api.model
    def _studio_field_types(self):
        """The types of a new field in this database: NEW_FIELD_TYPES, and
        GEO_TYPES where base_geoengine is installed."""
        types = NEW_FIELD_TYPES
        if self._studio_geo_available():
            types += studio_arch.GEO_TYPES
        return types

    def _studio_geo_view_missing(self, model):
        """Whether ``model`` has no geoengine view: none in the database and
        none a view line of the project adds. The form widget of a geometry
        field reads the raster layers of that view and fails without it."""
        if any(
            line.model == model and line.view_type == "geoengine"
            for line in self.view_line_ids
        ):
            return False
        return (
            not self.env["ir.ui.view"]
            .sudo()
            .search_count([("model", "=", model), ("type", "=", "geoengine")], limit=1)
        )

    @api.model
    def _studio_mail_available(self):
        """Whether a model can get a chatter: mail is installed. The studio
        does not depend on it."""
        return (
            "mail.thread" in self.env
            and "is_mail_thread" in self.env["ir.model"]._fields
        )

    def _studio_new_models(self):
        """The names of the models the project creates."""
        return set(self.new_model_ids.mapped("model"))

    @api.model
    def _studio_icon_module(self, icon):
        """The module whose icon ``icon`` names; ValidationError unless it is
        « <module>,static/description/icon.png » of an installed module."""
        match = _APP_ICON.match(icon or "")
        module = match and match.group(1)
        installed = module and self.env["ir.module.module"].sudo().search_count(
            [("name", "=", module), ("state", "=", "installed")]
        )
        if installed:
            try:
                file_path(f"{module}/static/description/icon.png")
                return module
            except (FileNotFoundError, ValueError):
                pass
        raise ValidationError(
            self.env._("%(icon)s is not the icon of an installed module.", icon=icon)
        )

    @api.model
    def _studio_app_icons(self):
        """The icons an app can take: [{value, label, url}] of the installed
        modules that have one, the studio first."""
        icons = []
        modules = (
            self.env["ir.module.module"].sudo().search([("state", "=", "installed")])
        )
        for module in modules:
            path = f"{module.name}/static/description/icon.png"
            try:
                file_path(path)
            except (FileNotFoundError, ValueError):
                continue
            icons.append(
                {
                    "value": f"{module.name},static/description/icon.png",
                    "label": module.shortdesc or module.name,
                    "url": f"/{path}",
                }
            )
        icons.sort(key=lambda i: (i["value"] != DEFAULT_APP_ICON, i["label"].lower()))
        return icons

    def _studio_check_menu(self, line):
        """Raise ValidationError when the model line ``line`` cannot have
        its menu: « app » needs an app of the project; « menu » needs a
        parent menu with an external id, outside the project, that opens no
        action."""
        self.ensure_one()
        if line.menu_mode == "app":
            if not line.app_id or line.app_id.project_id != self:
                raise ValidationError(
                    self.env._(
                        "The model %(model)s goes in an app of the project: "
                        "choose the app.",
                        model=line.model,
                    )
                )
            return
        parent = line.menu_parent_id.sudo()
        if not parent:
            raise ValidationError(
                self.env._(
                    "Choose the menu the model %(model)s goes under.",
                    model=line.model,
                )
            )
        if not parent.get_external_id().get(parent.id):
            raise ValidationError(
                self.env._(
                    "The menu %(menu)s has no external id: the module could "
                    "not refer to it.",
                    menu=parent.complete_name,
                )
            )
        if parent in self.created_menu_ids:
            raise ValidationError(
                self.env._(
                    "The menu %(menu)s is a menu of this project: choose « In "
                    "an app of the project ».",
                    menu=parent.complete_name,
                )
            )
        if parent.action:
            raise ValidationError(
                self.env._(
                    "The menu %(menu)s opens an action: a menu that opens an "
                    "action takes no submenu.",
                    menu=parent.complete_name,
                )
            )

    def _studio_check_rights_model(self, model):
        """Raise ValidationError unless an access row or a rule of the
        project can name ``model``: a model it creates, or a model of the
        database that stores records."""
        self.ensure_one()
        if model in self._studio_new_models():
            return
        Model = self.env.get(model) if model else None
        if (
            Model is None
            or Model._transient
            or Model._abstract
            or protected_model(model)
        ):
            raise ValidationError(
                self.env._(
                    "%(model)s cannot take access rights nor record rules "
                    "from a studio project.",
                    model=model,
                )
            )

    @api.model
    def _studio_group_xmlid(self, group):
        """The external id a generated module names the existing group
        ``group`` by: its first under an installed module, or the empty
        string. An id under « __export__ », or under a module the database
        does not have installed, names no module the generated module can
        depend on."""
        xmlids = group.sudo()._get_external_ids().get(group.id) or []
        modules = {xmlid.split(".", 1)[0] for xmlid in xmlids}
        installed = set(
            self.env["ir.module.module"]
            .sudo()
            .search(
                [
                    ("name", "in", sorted(modules)),
                    ("state", "in", ("installed", "to upgrade")),
                ]
            )
            .mapped("name")
        )
        return next((x for x in xmlids if x.split(".", 1)[0] in installed), "")

    @api.model
    def _studio_check_group(self, group):
        if not self._studio_group_xmlid(group):
            raise ValidationError(
                self.env._(
                    "The group %(group)s has no external id under an installed "
                    "module: the generated module could not refer to it.",
                    group=group.full_name,
                )
            )

    @api.model
    def _studio_share_groups(self, groups):
        """The groups of ``groups`` for users outside the company: the
        portal and public groups, the groups that imply them, and the
        groups marked « share »."""
        outside = self.env.ref("base.group_portal") | self.env.ref("base.group_public")
        return groups.sudo().filtered(
            lambda g: g.share or g in outside or g.trans_implied_ids & outside
        )

    def _studio_check_access_line(self, line):
        """Raise ValidationError when the access row ``line`` gives a share
        group (portal, public) more than reading a model the project does
        not create: it would open an existing model to the users outside
        the company."""
        self.ensure_one()
        if line.model in self._studio_new_models():
            return
        if not self._studio_share_groups(line.group_id):
            return
        if any(line[perm] for perm in SHARE_DENIED_PERMS):
            raise ValidationError(
                self.env._(
                    "The group %(group)s is for users outside the company: on "
                    "%(model)s, which the project does not create, it may only "
                    "read.",
                    group=line.group_id.full_name,
                    model=line.model,
                )
            )

    def _studio_check_rule(self, rule):
        """Raise UserError when the rule line ``rule`` does not apply. On a
        model the project does not create, a rule of a share group (portal,
        public) is refused: Odoo grants a user the union of the rules of
        its groups, so such a rule widens what these users reach."""
        if not any(rule[perm] for perm in PERMS):
            raise ValidationError(
                self.env._(
                    "The rule %(name)s applies to at least one operation.",
                    name=rule.name,
                )
            )
        shared = self._studio_share_groups(rule.group_ids)
        if shared and rule.model not in self._studio_new_models():
            raise ValidationError(
                self.env._(
                    "The rule %(name)s names groups of users outside the "
                    "company (%(groups)s) on %(model)s, which the project does "
                    "not create: it would widen what they reach.",
                    name=rule.name,
                    groups=", ".join(shared.mapped("full_name")),
                    model=rule.model,
                )
            )
        self._studio_rule_domain(rule.model, rule.domain_force, rule.name)

    def _studio_check_global_rule(self, rule):
        """Raise ValidationError when the rule line ``rule`` is global on a
        model the project does not create: a global rule restricts every
        user but the superuser, the Settings users included, in every
        database that installs the generated module."""
        self.ensure_one()
        if rule.global_rule and rule.model not in self._studio_new_models():
            raise ValidationError(
                self.env._(
                    "The rule %(name)s is on %(model)s, which the project does "
                    "not create: only a rule on a model of the project can be "
                    "global; choose its groups.",
                    name=rule.name,
                    model=rule.model,
                )
            )

    @api.model
    def _studio_rule_domain(self, model, text, name=None):
        """The domain of ``text`` evaluated as ir.rule evaluates it (``user``,
        ``company_ids``, ``time``...). On a model of the registry, its terms
        are checked against the fields of the model; on a model not created
        yet, or whose model line has an option whose field Apply has not
        created yet (``_studio_pending_option_fields``), only their shape.
        Raise UserError, naming the rule ``name``, when it does not
        apply."""
        try:
            if len(text or "") > RULE_DOMAIN_SIZE:
                raise ValueError(
                    self.env._("longer than %(size)s characters", size=RULE_DOMAIN_SIZE)
                )
            domain = safe_eval(text or "[]", self.env["ir.rule"]._eval_context())
            if not isinstance(domain, (list, tuple)):
                raise ValueError(self.env._("a domain is a list"))
            if model in self.env and not self._studio_pending_option_fields(model):
                with self.env.cr.savepoint():
                    expression.expression(list(domain), self.env[model].sudo())
            else:
                check_domain_shape(domain)
        except Exception as exc:  # noqa: BLE001 - any error is the message
            raise UserError(
                self.env._(
                    "The domain of the rule %(name)s does not apply: %(error)s",
                    name=name or model,
                    error=exc,
                )
            ) from exc
        return list(domain)

    def _studio_pending_option_fields(self, model):
        """The names of the fields of the options of the model line of
        ``model`` that its model in the registry does not have yet: Apply
        creates them. Empty for another model, or on no single project."""
        if len(self) != 1 or model not in self.env:
            return set()
        line = self.new_model_ids.filtered(lambda m: m.model == model)
        if not line:
            return set()
        return set(line._studio_option_fields()) - set(self.env[model]._fields)

    # ── state ───────────────────────────────────────────────────────────

    def _current_snapshot(self):
        """The JSON of the draft, to compare it with the one applied. A
        project with changes of views only keeps the form of a list of its
        changes, the one of the projects recorded before the models; the
        key « views » shows only with a view line, so that the snapshot of
        a project without one keeps the form it had before them."""
        self.ensure_one()
        changes = self.change_ids._snapshot()
        lines = (
            self.new_model_ids
            or self.access_line_ids
            or self.rule_line_ids
            or self.app_ids
            or self.group_line_ids
            or self.view_line_ids
        )
        if not lines:
            return json.dumps(changes, sort_keys=True)
        value = {
            "changes": changes,
            "models": self.new_model_ids._snapshot(),
            "access": self.access_line_ids._snapshot(),
            "rules": self.rule_line_ids._snapshot(),
            "apps": self.app_ids._snapshot(),
            "groups": self.group_line_ids._snapshot(),
        }
        if self.view_line_ids:
            value["views"] = self.view_line_ids._snapshot()
        return json.dumps(value, sort_keys=True)

    @api.model
    def _studio_load_snapshot(self, text):
        """The dict {changes, models, access, rules, apps, groups, views} of
        the snapshot ``text``, whichever form ``_current_snapshot`` gave it. A
        snapshot with a single « app » {name, icon, sequence} gives the app
        « menu_app », where its models « in the app » go; its rules without
        a group on a model it creates are global."""
        value = json.loads(text or "[]")
        if isinstance(value, list):
            value = {"changes": value}
        snapshot = {
            key: value.get(key) or []
            for key in (
                "changes",
                "models",
                "access",
                "rules",
                "apps",
                "groups",
                "views",
            )
        }
        app = value.get("app") or {}
        if "apps" not in value and (app.get("name") or "").strip():
            snapshot["apps"] = [
                {
                    "xml_name": "menu_app",
                    "name": app["name"],
                    "icon": app.get("icon") or "",
                    "menu_sequence": app.get("sequence") or 50,
                    "sequence": 10,
                }
            ]
        for item in snapshot["models"]:
            if "app" not in item and item.get("menu_mode") == "app":
                item["app"] = "menu_app"
        new_models = {item.get("model") for item in snapshot["models"]}
        for item in snapshot["rules"]:
            if "global_rule" not in item:
                item["global_rule"] = (
                    not item.get("group_ids") and item.get("model") in new_models
                )
        return snapshot

    def _touch(self):
        """After a change of the draft: new preview revision, new state."""
        for project in self:
            project._internal().draft_revision += 1
            project._update_state()

    def _update_state(self):
        for project in self:
            current = project._current_snapshot()
            if project.applied_snapshot and current == project.applied_snapshot:
                state = project._applied_state(current)
            else:
                state = "draft"
            if project.state != state:
                project._internal().state = state

    def _applied_state(self, snapshot):
        """The state of the project when ``snapshot``, the JSON of its
        changes, is the one applied to the database."""
        self.ensure_one()
        return "applied"

    def _editing(self):
        """The project as its editor operations change its changes: they
        touch the draft once, at the end."""
        return self.with_context(**{NO_TOUCH_KEY: True})

    # ── draft ───────────────────────────────────────────────────────────

    def _view_changes(self, view):
        """The changes of ``view``, a view, a pending view (see
        ``StudioPendingView``) or a view a view line adds (see
        ``StudioAddedView``), in the order they apply."""
        self.ensure_one()
        if is_pending_view(view):
            changes = self.change_ids.filtered(
                lambda c: c.model_line_id == view.line and c.view_type == view.type
            )
        elif is_added_view(view):
            changes = self.change_ids.filtered(lambda c: c.view_line_id == view.line)
        else:
            changes = self.change_ids.filtered(lambda c: c.view_id == view)
        return changes.sorted(lambda c: (c.sequence, c.id))

    def _change_view(self, change):
        """The view ``change`` is on: its view, the pending view of its
        model line, or the view its view line adds."""
        if change.view_id:
            return change.view_id
        if change.view_line_id:
            return added_view(change.view_line_id)
        return pending_view(change.model_line_id, change.view_type)

    def _base_arch(self, view, branding=False):
        """The combined arch of ``view`` without the views of the project;
        of a pending view, the default arch of its model line; of a view a
        view line adds, the arch the line recorded."""
        self.ensure_one()
        if is_pending_view(view):
            return etree.fromstring(self._studio_default_arch(view.line, view.type))
        if is_added_view(view):
            return etree.fromstring(view.line.arch)
        context = {EXCLUDE_KEY: ViewExclusion(self.studio_view_ids.ids)}
        if branding:
            context["inherit_branding"] = True
        View = self.env["ir.ui.view"].sudo().with_context(**context)
        return View.browse(view.id)._get_combined_arch()

    def _draft_arch(self, view, track=False):
        """(arch, errors): the base arch of ``view`` with the changes of the
        project applied; ``errors`` maps a change id to why it does not
        apply. ``track``: the nodes the changes touch carry
        ``arch.CHANGE_MARK``, for the editor only."""
        self.ensure_one()
        return self._draft_arch_without(
            view, self.env["erplibre.studio.change"], track=track
        )

    def _draft_arch_without(self, view, skipped, track=False):
        """``_draft_arch`` of ``view`` with the changes ``skipped`` left
        out. On a pending view, a change that shows a field the model will
        not have (the inverse of a one2many that left the draft) does not
        apply."""
        self.ensure_one()
        changes = self._view_changes(view) - skipped
        errors = {}
        if is_pending_view(view):
            known = set(self._studio_simulated_fields(view.line))
            for change in changes.filtered(
                lambda c: c.change_type == "add_existing_field"
                and c.field_name not in known
            ):
                errors[change.id] = self.env._(
                    "The field %(name)s is not a field of %(model)s.",
                    name=change.field_name,
                    model=view.model,
                )
        arch, arch_errors = studio_arch.apply_changes(
            self._base_arch(view),
            [c._as_dict() for c in changes if c.id not in errors],
            view.type,
            self._arch_message,
            track=track,
        )
        return arch, {**arch_errors, **errors}

    @api.model
    def _preview_project(self):
        """The project whose draft get_views shows: the one named by the
        context, when the user is its editor."""
        value = self.env.context.get(PREVIEW_KEY)
        if not value:
            return self.browse()
        try:
            project_id = int(str(value).split(":", 1)[0])
        except ValueError:
            return self.browse()
        project = self.sudo().browse(project_id).exists()
        if (
            not project
            or project.user_id != self.env.user
            or not self.env.user.has_group("base.group_system")
        ):
            return self.browse()
        return project

    def _preview_arch(self, arch, view, model):
        """``arch`` (the combined arch of ``view``, without the project
        views) with the draft applied. A new field not yet in the database
        shows as a placeholder in a form and is left out of the other view
        types, root attributes of a map that name it included: the map
        would read a field the model does not have."""
        self.ensure_one()
        changes = [c._as_dict() for c in self._view_changes(view)]
        if not changes:
            return arch
        arch, _errors = studio_arch.apply_changes(
            arch, changes, view.type, self._arch_message
        )
        Model = self.env[model]
        pending = {
            c.field_name: c._payload().get("field") or {}
            for c in self.change_ids
            if c.change_type == "add_field" and c.model == model
        }
        for node in list(arch.iter("field")):
            name = node.get("name")
            if name not in pending or name in Model._fields:
                continue
            parent = node.getparent()
            if view.type != "form":
                remove_keeping_tail(node)
                continue
            placeholder = etree_placeholder(
                pending[name].get("field_description") or name,
                self.env._("new field, created by Apply"),
            )
            placeholder.tail = node.tail
            parent.replace(node, placeholder)
        if view.type == "leaflet_map":
            for attribute in studio_arch.LEAFLET_FIELD_ATTRIBUTES:
                name = arch.get(attribute)
                if name in pending and name not in Model._fields:
                    del arch.attrib[attribute]
        return arch

    # ── operations of the editor ────────────────────────────────────────

    def _next_sequence(self):
        return max(self.change_ids.mapped("sequence") or [0]) + 10

    def _project_field_changes(self, model=None):
        return self.change_ids.filtered(
            lambda c: c.change_type == "add_field" and (not model or c.model == model)
        )

    def _taken_field_names(self, model):
        """The field names a new field of ``model`` cannot take: those of the
        model (simulated for a model not created yet), those of the options
        of its model line, those the projects add to it, and the inverse
        fields their one2many and many2one create on it."""
        line = self._studio_pending_line(model)
        if line:
            names = set(self._studio_simulated_fields(line))
        else:
            names = set(self.env[model]._fields)
        # The fields of the options that are on, before Apply creates them.
        for option in self.new_model_ids.filtered(lambda m: m.model == model):
            names |= set(option._studio_option_fields())
        Change = self.env["erplibre.studio.change"]
        names |= set(
            Change.search(
                [("model", "=", model), ("change_type", "=", "add_field")]
            ).mapped("field_name")
        )
        for change in Change.search(
            [
                ("change_type", "=", "add_field"),
                "|",
                ("payload", "ilike", "inverse_new"),
                ("payload", "ilike", "inverse_o2m"),
            ]
        ):
            field = change._payload().get("field") or {}
            inverse = self._studio_inverse_definition(change.model, field)
            if inverse and field.get("relation") == model:
                names.add(inverse[0])
        return names

    def _clean_field_definition(self, model, field, name=None, existing=None):
        """A checked definition of a new field: {ttype, field_description,
        readonly, help, translate, index, size, selection, relation,
        on_delete, inverse_o2m, relation_field, inverse_new, relation_table,
        column1, column2, currency_field}; translate, index and size only
        when set (``_clean_field_options``). ``name`` is the field name;
        None makes one from the label. ``existing``: the definition the field had, whose relation an
        x2many keeps, and a many2one while it has an inverse one2many."""
        ttype = field.get("ttype")
        if ttype not in self._studio_field_types():
            raise UserError(self.env._("Unknown field type %(type)s.", type=ttype))
        label = (field.get("field_description") or "").strip()
        label = label or self.env._("New field")
        help_text = (field.get("help") or "").strip()
        self._check_field_texts(label, help_text)
        name = self._clean_field_name(model, label, field, name)
        # « Required » stays on the view node: on the model it would set
        # NOT NULL on a table that has rows.
        definition = {
            "ttype": ttype,
            "field_description": label,
            "readonly": bool(field.get("readonly")),
            "help": help_text,
        }
        definition.update(self._clean_field_options(ttype, field))
        if ttype == "selection":
            definition["selection"] = self._clean_selection(field)
        elif ttype == "many2one":
            definition["relation"] = self._clean_relation(field)
            definition["on_delete"] = self._clean_on_delete(field)
            inverse = self._clean_many2one_inverse(
                model, name, definition["relation"], field, existing
            )
            if inverse:
                definition["inverse_o2m"] = inverse
        elif ttype == "monetary":
            definition["currency_field"] = self._clean_currency(model, field)
        elif ttype in studio_arch.X2MANY_TYPES and existing:
            definition.update(self._kept_relation(name, field, existing))
        elif ttype == "one2many":
            definition.update(self._clean_one2many(model, name, field))
        elif ttype == "many2many":
            definition.update(self._clean_many2many(model, name, field))
        return name, definition

    @api.model
    def _clean_field_options(self, ttype, field):
        """{translate, index, size} of the field definition ``field`` of type
        ``ttype``, each key only when set: a definition without the options
        stays as it was before they existed. A false or empty value is no
        option. UserError on an option ``ttype`` does not take
        (FIELD_OPTIONS), on a field both translatable and indexed, and on a
        size that is not a whole number from 1 to MAX_FIELD_SIZE."""
        options = {}
        for key in ("translate", "index"):
            if field.get(key):
                options[key] = True
        size = field.get("size")
        if size not in (None, False, "", 0):
            if isinstance(size, bool):
                size = None
            else:
                try:
                    size = int(size)
                except (TypeError, ValueError):
                    size = None
            if size is None or not 0 < size <= MAX_FIELD_SIZE:
                raise UserError(
                    self.env._(
                        "The maximum size is a whole number from 1 to %(max)s.",
                        max=MAX_FIELD_SIZE,
                    )
                )
            options["size"] = size
        labels = {
            "translate": self.env._("Translatable"),
            "index": self.env._("Indexed"),
            "size": self.env._("Maximum size"),
        }
        for key in options:
            if ttype not in FIELD_OPTIONS[key]:
                raise UserError(
                    self.env._(
                        "A field of type %(type)s does not take the option "
                        "%(option)s.",
                        type=ttype,
                        option=labels[key],
                    )
                )
        if options.get("translate") and options.get("index"):
            raise UserError(
                self.env._("A translatable field cannot be indexed as well.")
            )
        return options

    @api.model
    def _check_field_texts(self, label, help_text):
        """Raise UserError when the label or the tooltip of a new field
        cannot be recorded. Every text is accepted here; a module that
        copies them elsewhere narrows the check."""

    def _clean_field_name(self, model, label, field, name):
        """The technical name of a new field of ``model``. ``name``: the
        name of a field of the draft, checked for its format only; None
        takes ``field["name"]``, else proposes one made of ``label``, and
        refuses it on the first problem ``_studio_field_name_problem``
        finds."""
        if name is None:
            name = field.get("name") or studio_arch.field_name_from_label(
                label, self._taken_field_names(model)
            )
            problem = self._studio_field_name_problem(model, name)
            if problem:
                raise UserError(problem["message"])
            return name
        if not studio_arch.valid_field_name(name, prefix_required=False):
            raise UserError(
                self.env._(
                    "%(name)s is not a valid field name: lower case letters, "
                    "digits and underscores.",
                    name=name,
                )
            )
        return name

    # ── technical names of the new fields ───────────────────────────────

    @api.model
    def _studio_field_name_rule(self):
        """The rule the technical names of new fields follow on this
        database: {prefix_required, mode, label, text, detail}. ``label``
        names the rule; ``text`` and ``detail`` say why a name without the
        prefix is refused."""
        return {
            "prefix_required": True,
            "mode": "production",
            "label": self.env._("Production · x_ required"),
            "text": self.env._("Prefix x_ required on this database"),
            "detail": self.env._(
                "Fields created outside the code carry x_ on a production database."
            ),
        }

    def _studio_reserved_field_names(self, model):
        """The names a field of ``model`` cannot take without hiding a method
        or an attribute: those of every model; for a model of the registry,
        those of the classes the field lands on (``delegation_classes``);
        for a model the project creates and has not applied yet, « pool »,
        which the registry sets on every class, and with the chatter those
        of CHATTER_MODELS. Fields are not reserved, they are taken
        (``_studio_field_name_owner``)."""
        registry = self.env.registry
        names = attribute_names(models.Model)
        line = self._studio_pending_line(model)
        if line:
            names.add("pool")
            mixins = CHATTER_MODELS if line.chatter else ()
            classes = [registry[name] for name in mixins if name in registry]
        else:
            classes = delegation_classes(registry, model)
        for cls in classes:
            names |= attribute_names(cls)
        return names

    def _studio_project_field_names(self, model):
        """[(name, change)] of the new fields of the project on ``model``:
        those its add_field changes add, and the inverse fields its one2many
        and many2one create on ``model``. A name given by two changes is
        listed twice."""
        self.ensure_one()
        result = []
        for change in self._project_field_changes():
            definition = change._payload().get("field") or {}
            if change.model == model:
                result.append((change.field_name, change))
            inverse = self._studio_inverse_definition(change.model, definition)
            if inverse and definition.get("relation") == model:
                result.append((inverse[0], change))
        return result

    def _studio_own_applied_field(self, model, name):
        """Whether the field ``name`` of ``model`` in the database is one the
        project created: in its fields, or defined by its module."""
        field = self.env["ir.model.fields"].sudo()._get(model, name)
        return bool(
            field
            and (
                field in self.field_ids
                or self._module_of("ir.model.fields", field.id) == self.module_name
            )
        )

    @api.model
    def _studio_inheriting_owner(self, model, name):
        """The model of the registry that inherits ``model`` by delegation
        (``_inherits``, at any depth) and already has a field ``name`` of its
        own or of another parent, or None. A field added to ``model`` shows
        on these models too, where it would collide; the fields they take
        from ``model`` itself are no collision. The registry gives the
        descendants on each call: a module installed in between counts."""
        registry = self.env.registry
        if model not in registry:
            return None
        for child in registry.descendants([model], "_inherits"):
            if child == model:
                continue
            field = self.env[child]._fields.get(name)
            if field is not None and field.base_field.model_name != model:
                return child
        return None

    @api.model
    def _studio_delegation_models(self, model):
        """{name: kind} of the models of the registry that share the fields
        of ``model`` by delegation (``_inherits``, at any depth): « child »
        for those that inherit it, « parent » for those it inherits. A new
        field on one of them and a new field of the same name on ``model``
        end up on the same class, one hiding the other."""
        registry = self.env.registry
        if model not in registry:
            return {}
        result = {
            name: "child"
            for name in registry.descendants([model], "_inherits")
            if name != model
        }
        todo = list(registry[model]._inherits)
        while todo:
            parent = todo.pop()
            if parent == model or parent in result or parent not in registry:
                continue
            result[parent] = "parent"
            todo.extend(registry[parent]._inherits)
        return result

    def _studio_field_name_owner(self, model, name, own=None):
        """Who already holds the field name ``name`` on ``model``, the field
        of the project named ``own`` aside (the one renamed or checked):
        None, or {kind, project, model}. ``kind``: « project » when another
        new field of this project takes it, « model » when the model has it
        (a field the project created is its own), « child » when a model
        that inherits ``model`` by delegation has it, ``model`` naming that
        model (``_studio_inheriting_owner``), « other » when the draft of
        another project adds it, ``project`` naming that project. A new
        field of a draft, of this project or another, on a model that
        shares the fields of ``model`` by delegation
        (``_studio_delegation_models``) gives « child » or « parent », with
        ``model`` and ``project``."""
        self.ensure_one()
        mine = [n for n, _change in self._studio_project_field_names(model)]
        if mine.count(name) - (name == own) > 0:
            return {"kind": "project", "project": self.name}
        line = self._studio_pending_line(model)
        if line:
            existing = set(self._studio_simulated_fields(line)) - set(mine)
        else:
            Model = self.env.get(model)
            existing = set(Model._fields) if Model is not None else set()
        if name in existing and (
            line or not self._studio_own_applied_field(model, name)
        ):
            return {"kind": "model", "project": False}
        child = self._studio_inheriting_owner(model, name)
        if child:
            return {"kind": "child", "project": False, "model": child}
        related = self._studio_delegation_models(model)
        for other, kind in related.items():
            if any(n == name for n, _change in self._studio_project_field_names(other)):
                return {"kind": kind, "project": self.name, "model": other}
        targets = [model, *related]
        Change = self.env["erplibre.studio.change"]
        others = Change.search(
            [
                ("change_type", "=", "add_field"),
                ("project_id", "!=", self.id),
                "|",
                "&",
                ("model", "in", targets),
                ("field_name", "=", name),
                "|",
                ("payload", "ilike", "inverse_new"),
                ("payload", "ilike", "inverse_o2m"),
            ]
        )
        for change in others:
            project = change.project_id
            for target, field_name in project._studio_change_field_names(change):
                if field_name != name or target not in targets:
                    continue
                if target in related:
                    return {
                        "kind": related[target],
                        "project": project.name,
                        "model": target,
                    }
                return {"kind": "other", "project": project.name}
        return None

    def _studio_field_name_status(self, model, name, own=None):
        """{code, owner, message, detail, checks} of the technical name
        ``name`` of a new field of ``model``, the field named ``own`` aside
        (see ``_studio_field_name_owner``). ``code``: None when the name
        applies, else the first of FIELD_NAME_CHECKS that fails.
        ``checks``: [{key, ok, text}], the checks of FIELD_NAME_CHECKS each
        run on its own; the name is looked for in the model and the
        projects only when its format is valid."""
        self.ensure_one()
        rule = self._studio_field_name_rule()
        passed = studio_arch.field_name_checks(
            name,
            rule["prefix_required"],
            self._studio_reserved_field_names(model),
        )
        owner = None
        if passed["format"]:
            owner = self._studio_field_name_owner(model, name, own)
        passed["unique"] = passed["format"] and owner is None
        label = self._studio_model_label(model)
        texts = {
            "format": self.env._("Lower case letters, digits and _"),
            "reserved": self.env._("Not a reserved word of the ORM"),
            "prefix": self.env._("Prefix that fits the rule of the database"),
            "unique": self.env._(
                "Unique on %(model)s and in the projects", model=label
            ),
        }
        code = next((key for key in FIELD_NAME_CHECKS if not passed[key]), None)
        if code is None:
            message = self.env._("Available")
            detail = self.env._(
                "No field %(name)s on %(model)s nor in the other projects.",
                name=name,
                model=label,
            )
        elif code == "format":
            message = self.env._(
                "Invalid format: lower case letters, digits and _ only"
            )
            detail = self.env._("Starts with a letter, 63 characters at most.")
        elif code == "reserved":
            message = self.env._("Reserved name of the ORM (%(name)s)", name=name)
            detail = self.env._(
                "This name would hide a method or an attribute of the model. "
                "The x_ prefix avoids this case."
            )
        elif code == "prefix":
            message, detail = rule["text"], rule["detail"]
        elif owner["kind"] == "project":
            message = self.env._(
                "%(name)s is already created by this project", name=name
            )
            detail = self.env._("Each new field of the project needs its own name.")
        elif owner["kind"] == "other":
            message = self.env._(
                "The field %(name)s already exists in another project " "(%(project)s)",
                name=name,
                project=owner["project"],
            )
            detail = self.env._("Two Apply would create the same column.")
        elif owner["kind"] == "child":
            message = self.env._(
                "The field %(name)s already exists on %(model)s, which "
                "inherits %(parent)s",
                name=name,
                model=self._studio_model_label(owner["model"]),
                parent=label,
            )
            detail = self.env._(
                "A field of %(parent)s also shows on the models that inherit it.",
                parent=label,
            )
        elif owner["kind"] == "parent":
            parent = self._studio_model_label(owner["model"])
            message = self.env._(
                "The field %(name)s already exists on %(model)s, which "
                "%(child)s inherits",
                name=name,
                model=parent,
                child=label,
            )
            detail = self.env._(
                "A field of %(parent)s also shows on the models that inherit it.",
                parent=parent,
            )
        else:
            message = self.env._(
                "The field %(name)s already exists on %(model)s",
                name=name,
                model=label,
            )
            detail = self.env._("Add the existing field, or choose another name.")
        return {
            "code": code,
            "owner": owner,
            "message": message,
            "detail": detail,
            "checks": [
                {"key": key, "ok": passed[key], "text": texts[key]}
                for key in FIELD_NAME_CHECKS
            ],
        }

    def _studio_field_name_problem(self, model, name, own=None):
        """The ``_studio_field_name_status`` of ``name`` when it does not
        apply, else None."""
        status = self._studio_field_name_status(model, name, own)
        return status if status["code"] else None

    def _studio_change_field_names(self, change):
        """[(model, name)] of the new fields the add_field ``change`` makes:
        its field, and the inverse field it creates on its comodel."""
        definition = change._payload().get("field") or {}
        result = [(change.model, change.field_name or "")]
        inverse = self._studio_inverse_definition(change.model, definition)
        if inverse:
            result.append((definition["relation"], inverse[0]))
        return result

    def _studio_field_name_problems(self):
        """[{change_id, model, name, message}]: the new fields of the project
        whose technical name does not apply, each checked against the other
        fields (``_studio_field_name_problem`` with itself aside)."""
        self.ensure_one()
        result = []
        for change in self._project_field_changes():
            for model, name in self._studio_change_field_names(change):
                problem = self._studio_field_name_problem(model, name, own=name)
                if problem:
                    result.append(
                        {
                            "change_id": change.id,
                            "model": model,
                            "name": name,
                            "message": problem["message"],
                        }
                    )
        return result

    def _clean_selection(self, field):
        """[[value, label]]: non-empty values, each once."""
        selection = []
        for item in field.get("selection") or []:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                continue
            value, text = (str(item[0]).strip(), str(item[1]).strip())
            if value and value not in [s[0] for s in selection]:
                selection.append([value, text or value])
        return selection or [["value_1", self.env._("Value 1")]]

    def _clean_relation(self, field):
        """The comodel of a new relational field: a model of the registry,
        or a model the project creates, which Apply creates first."""
        relation = field.get("relation") or "res.partner"
        if relation in self._studio_new_models():
            return relation
        Comodel = self.env.get(relation)
        if Comodel is None or Comodel._transient or Comodel._abstract:
            raise UserError(
                self.env._("%(model)s cannot be the comodel.", model=relation)
            )
        return relation

    @api.model
    def _clean_on_delete(self, field):
        value = field.get("on_delete") or "set null"
        if value not in ON_DELETE:
            raise UserError(self.env._("Invalid value %(value)s.", value=value))
        return value

    def _clean_currency(self, model, field):
        """The many2one to res.currency of a monetary field: the one given,
        else the ``currency_id`` of the model; on a model not created yet,
        one of its new fields."""
        line = self._studio_pending_line(model)
        if line:
            infos = self._studio_simulated_fields(line)
        else:
            infos = {
                name: {"type": f.type, "relation": f.comodel_name}
                for name, f in self.env[model]._fields.items()
            }
        currency = field.get("currency_field") or next(
            (n for n in ("currency_id", "x_currency_id") if n in infos),
            "",
        )
        target = infos.get(currency) or {}
        if not (
            target.get("type") == "many2one"
            and target.get("relation") == "res.currency"
        ):
            raise UserError(
                self.env._(
                    "A monetary field needs a many2one to res.currency on "
                    "%(model)s.",
                    model=model,
                )
            )
        return currency

    def _refuse(self, refusal):
        """Raise the UserError of ``refusal``, an ArchError or None."""
        if refusal is not None:
            raise UserError(self._arch_message(refusal))

    def _check_drop(self, arch, op, view_type):
        target = op.get("target")
        position = op.get("position") or "after"
        node = self._locate(arch, target)
        self._refuse(studio_arch.drop_refusal(view_type, node, position))
        return target, position, node

    def _locate(self, arch, xpath):
        try:
            return studio_arch.locate(arch, xpath or "")
        except studio_arch.ArchError as exc:
            raise UserError(self._arch_message(exc)) from exc

    @api.model
    def _arch_message(self, exc):
        """The message of ``exc`` in the user's language: an ``ArchError``
        by its code, any other exception as it reads."""
        code = getattr(exc, "code", None)
        params = getattr(exc, "params", {})
        messages = {
            "no_node": lambda: self.env._("No node at %(xpath)s.", **params),
            "invalid_xpath": lambda: self.env._(
                "Invalid XPath %(xpath)s: %(error)s", **params
            ),
            "unknown_change": lambda: self.env._(
                "Unknown change type %(type)s.", **params
            ),
            "unknown_position": lambda: self.env._(
                "Unknown position %(position)s.", **params
            ),
            "no_drop_inside": lambda: self.env._(
                "Nothing can be dropped inside <%(tag)s>.", **params
            ),
            "no_drop": lambda: self.env._("Nothing can be dropped there."),
            "chain": lambda: self.env._(
                "Nothing can be dropped between the nodes of a t-if chain."
            ),
            "no_move": lambda: self.env._("<%(tag)s> cannot move.", **params),
            "chain_move": lambda: self.env._("A node of a t-if chain cannot move."),
            "outside_template": lambda: self.env._(
                "This field is loaded by the view for its templates: it "
                "cannot move nor be hidden."
            ),
            "no_hide_root": lambda: self.env._("The view itself cannot be hidden."),
            "no_hide": lambda: self.env._("<%(tag)s> cannot be hidden.", **params),
            "chain_hide": lambda: self.env._(
                "The t-if or the t-elif of a chain cannot be hidden."
            ),
            "content_directive": lambda: self.env._(
                "<%(tag)s> replaces its content: nothing dropped into it shows.",
                **params,
            ),
            "template_move": lambda: self.env._(
                "A node of a template cannot move out of the templates."
            ),
            "unsafe_attribute": lambda: self.env._(
                "A change cannot write the attribute %(attribute)s.", **params
            ),
            "unknown_node": lambda: self.env._(
                "A change cannot add <%(tag)s>.", **params
            ),
            "bad_operator": lambda: self.env._(
                "The operator %(operator)s does not apply to a %(type)s field.",
                **params,
            ),
            "bad_color": lambda: self.env._("Invalid color %(color)s.", **params),
            "bad_color_operator": lambda: self.env._(
                "Invalid operator %(operator)s.", **params
            ),
            "bad_color_value": lambda: self.env._(
                "The value %(value)s cannot be used in a timeline color: it "
                "holds « : » or « ; ».",
                **params,
            ),
            "bad_field": lambda: self.env._("Invalid field %(field)s.", **params),
            "bad_order": lambda: self.env._("Invalid order %(order)s.", **params),
            "unknown_view_type": lambda: self.env._(
                "The studio makes no default %(type)s view.", **params
            ),
            "page_place": lambda: self.env._("A tab goes in a notebook."),
            "notebook_place": lambda: self.env._(
                "A notebook goes in a sheet or in a tab."
            ),
            "x2many_view": lambda: self.env._("A one2many shows in a form only."),
            "many2many_view": lambda: self.env._(
                "A many2many shows in a form, a list or a kanban only."
            ),
            "geo_view": lambda: self.env._(
                "A geo field shows as a map in a form only."
            ),
            "geo_info_box": lambda: self.env._(
                "A geo field goes among the fields a GeoEngine view loads, "
                "not in its info box."
            ),
        }
        if code in messages:
            return messages[code]()
        return str(exc)

    def _add_change(self, view, change_type, xpath, position, payload):
        Change = self.env["erplibre.studio.change"].with_context(**{NO_TOUCH_KEY: True})
        target = {"view_id": view.id}
        if is_pending_view(view):
            target = {"view_id": False, "model_line_id": view.line.id}
        elif is_added_view(view):
            target = {"view_id": False, "view_line_id": view.line.id}
        return Change.create(
            {
                "project_id": self.id,
                "sequence": self._next_sequence(),
                "change_type": change_type,
                "model": view.model,
                **target,
                "view_type": view.type,
                "xpath": xpath,
                "position": position,
                "payload": json.dumps(payload, sort_keys=True),
            }
        )

    def _field_add_change(self, model, name):
        return self._project_field_changes(model).filtered(
            lambda c: c.field_name == name
        )[:1]

    @api.model
    def _view_types(self):
        """The view types the studio edits in this database: those of
        ``VIEW_TYPES`` that ir.ui.view knows. « timeline » is one only when
        a module (web_timeline) adds it."""
        known = self.env["ir.ui.view"]._fields["type"].get_values(self.env)
        return tuple(t for t in studio_arch.VIEW_TYPES if t in known)

    def _apply_operation(self, view, op):
        """Record the editor operation ``op`` (a dict with a ``type``) on
        ``view`` as a change, or update the change it refines. Return the
        change touched, or an empty recordset. Raise UserError when the
        operation does not fit the draft arch."""
        self.ensure_one()
        self = self._editing()
        if view.type not in self._view_types():
            raise UserError(
                self.env._("The studio does not edit %(type)s views.", type=view.type)
            )
        otype = op.get("type")
        handlers = {
            "add_field": self._op_add_field,
            "add_existing_field": self._op_add_existing_field,
            "add_filter": self._op_add_filter,
            "add_group_by": self._op_add_group_by,
            "add_separator": self._op_add_separator,
            "add_group": self._op_add_group,
            "add_page": self._op_add_page,
            "add_widget": self._op_add_widget,
            "move": self._op_move,
            "update_field": lambda view, arch, op: self._update_field(view, op),
            "rename_field": lambda view, arch, op: self._studio_rename_field(view, op),
            "remove": self._remove_node,
            "hide": self._op_hide,
            "set_attribute": self._op_set_attribute,
        }
        for name in studio_arch.ATTRIBUTE_CHANGES:
            handlers[name] = self._attribute_operation
        if otype not in handlers:
            raise UserError(self.env._("Unknown operation %(type)s.", type=otype))
        if otype not in studio_arch.VIEW_OPERATIONS[view.type]:
            raise UserError(
                self.env._(
                    "The operation %(type)s does not apply to a %(view_type)s view.",
                    type=otype,
                    view_type=view.type,
                )
            )
        if is_pending_view(view) and otype not in PENDING_VIEW_OPERATIONS.get(
            view.type, ()
        ):
            raise UserError(
                self.env._(
                    "Apply the model first: %(type)s needs its records.", type=otype
                )
            )
        arch, _errors = self._draft_arch(view)
        change = handlers[otype](view, arch, op)
        self._touch()
        if change.exists():
            _arch, errors = self._draft_arch(view)
            if change.id in errors:
                raise UserError(errors[change.id])
        return change.exists()

    # ── fields named by an operation ────────────────────────────────────

    @api.model
    def _field_info(self, model, name):
        """The ``fields_get`` description of the field ``name`` of
        ``model``; UserError when the model has no such field."""
        line = self._studio_pending_line(model) if self else None
        if line:
            info = self._studio_simulated_fields(line).get(name or "")
            if not info:
                raise UserError(self.env._("Unknown field %(name)s.", name=name))
            return info
        Model = self.env[model]
        if not name or name not in Model._fields:
            raise UserError(self.env._("Unknown field %(name)s.", name=name))
        return Model.fields_get([name], attributes=FIELD_INFO)[name]

    def _studio_pending_line(self, model):
        """The model line of the project that creates ``model``, while not
        applied; else an empty recordset."""
        lines = self.new_model_ids if len(self) == 1 else self.new_model_ids.browse()
        return lines.filtered(lambda line: line.model == model and not line.applied)[:1]

    def _studio_field_names(self, model):
        """The names of the fields of ``model``, simulated for a model of the
        project not created yet."""
        line = self._studio_pending_line(model)
        if line:
            return set(self._studio_simulated_fields(line))
        return set(self.env[model]._fields)

    def _check_groupable(self, model, name):
        info = self._field_info(model, name)
        if not info.get("groupable"):
            raise UserError(
                self.env._("The records cannot be grouped by %(name)s.", name=name)
            )
        return info

    def _check_interval(self, info, interval):
        """``interval`` checked against the field ``info``; None for none."""
        if not interval:
            return None
        if interval not in studio_arch.INTERVALS:
            raise UserError(
                self.env._("Unknown interval %(interval)s.", interval=interval)
            )
        if info["type"] not in studio_arch.DATE_TYPES:
            raise UserError(self.env._("Only a date field takes an interval."))
        return interval

    def _check_pivot_axis(
        self, model, name, axis, interval=None, axes=studio_arch.PIVOT_AXES
    ):
        """The attributes {type, interval} of the field ``name`` of a pivot
        or a graph on ``axis``, one of ``axes`` (see ``AXIS_VIEW_TYPES``):
        a measure adds up a number, a row or a column groups."""
        if axis not in axes:
            raise UserError(
                self.env._(
                    "Choose the axis of the field: row, column or measure.",
                )
            )
        info = self._field_info(model, name)
        if axis == "measure":
            if info["type"] not in studio_arch.NUMBER_TYPES or not info.get(
                "aggregator"
            ):
                raise UserError(
                    self.env._(
                        "%(name)s cannot be a measure: a measure adds up a "
                        "number field.",
                        name=name,
                    )
                )
            if interval:
                raise UserError(self.env._("A measure takes no interval."))
            return {"type": axis}
        self._check_groupable(model, name)
        attrs = {"type": axis}
        interval = self._check_interval(info, interval)
        if interval:
            attrs["interval"] = interval
        return attrs

    def _typed_value(self, info, value):
        """``value``, typed as the field ``info`` stores it, for a search
        filter or a timeline color rule."""
        ttype = info["type"]
        try:
            if ttype == "boolean":
                if isinstance(value, str):
                    return value.strip().lower() in ("1", "true", "yes")
                return bool(value)
            if ttype == "integer":
                return int(value)
            if ttype in ("float", "monetary"):
                return float(value)
            if ttype == "date":
                return fields.Date.to_string(fields.Date.to_date(value))
            if ttype == "datetime":
                return fields.Datetime.to_string(fields.Datetime.to_datetime(value))
            if ttype == "selection":
                if value not in [item[0] for item in info.get("selection") or []]:
                    raise ValueError(value)
                return value
            text = str(value if value is not None else "").strip()
            if not text:
                raise ValueError(value)
            return text
        except (TypeError, ValueError):
            raise UserError(
                self.env._(
                    "%(value)s is not a value of the field %(name)s.",
                    value=value,
                    name=info.get("string"),
                )
            ) from None

    def _check_domain(self, model, terms):
        """Raise UserError when the domain of ``terms`` does not search
        ``model``."""
        try:
            with self.env.cr.savepoint():
                self.env[model].sudo()._search([tuple(term) for term in terms])
        except (ValueError, KeyError, TypeError) as exc:
            raise UserError(
                self.env._("The filter does not apply: %(error)s", error=exc)
            ) from exc

    @api.model
    def _clean_widget(self, name):
        if not name or not re.match(r"^[a-z][a-z0-9_]*$", name):
            raise UserError(self.env._("Invalid widget %(name)s.", name=name))
        return name

    # ── operations of the editor, by type ───────────────────────────────

    def _op_add_field(self, view, arch, op):
        """A new field dropped into the view; an x2many shows as an inline
        sub-list in a form, a many2many as tags in a list or a kanban. On a
        map, the field of a lane: ``attribute`` names the root attribute it
        becomes (``_leaflet_new_field``)."""
        target, position, _node = self._check_drop(arch, op, view.type)
        field = op.get("field") or {}
        self._refuse(studio_arch.x2many_refusal(view.type, field.get("ttype")))
        self._refuse(studio_arch.geo_refusal(view.type, field.get("ttype")))
        root_attribute = None
        if view.type == "leaflet_map":
            root_attribute = self._leaflet_new_field(op, target, position)
        name, definition = self._clean_field_definition(view.model, field)
        payload = {
            "field_name": name,
            "field": definition,
            "node_attrs": {},
            # The name follows the label until it is given or renamed.
            "name_auto": not field.get("name"),
        }
        if root_attribute:
            payload["root_attribute"] = root_attribute
        if definition["ttype"] in studio_arch.X2MANY_TYPES:
            attrs, children = studio_arch.x2many_node(
                view.type,
                definition["ttype"],
                self._studio_display_field(definition["relation"]),
            )
            payload["node_attrs"] = attrs
            if children:
                payload["node_children"] = children
        return self._add_change(view, "add_field", target, position, payload)

    def _leaflet_new_field(self, op, target, position):
        """The root attribute of a map the new field of ``op`` becomes: its
        ``attribute``, a field attribute of the map whose kind takes a new
        field of the type of ``op`` (LEAFLET_NEW_FIELD_TYPES), dropped at
        the end of the root. UserError otherwise: a map ignores a field
        that no attribute names."""
        attribute = op.get("attribute")
        settable = studio_arch.SETTABLE_ATTRIBUTES["leaflet_map"]["leaflet_map"]
        types = studio_arch.LEAFLET_NEW_FIELD_TYPES.get(settable.get(attribute), ())
        if (
            target != "/leaflet_map"
            or position != "inside"
            or attribute not in studio_arch.LEAFLET_FIELD_ATTRIBUTES
        ):
            raise UserError(
                self.env._(
                    "A map shows a new field through one of its lanes only: "
                    "drop it on a lane."
                )
            )
        ttype = (op.get("field") or {}).get("ttype")
        if ttype not in types:
            raise UserError(
                self.env._(
                    "This lane of the map takes no new %(type)s field.", type=ttype
                )
            )
        return attribute

    def _field_scope(self, arch, node, view_type):
        """The names of the fields a new field must not repeat: those of the
        template the drop lands in, or of the view outside the templates;
        the whole arch for the other view types."""
        if view_type not in studio_arch.TEMPLATED_TYPES:
            return studio_arch.arch_field_names(arch)
        for item in [node, *node.iterancestors()]:
            if studio_arch.is_template(item):
                return studio_arch.template_field_names(view_type, item)
        return self._loaded_fields(arch)

    @api.model
    def _in_template_drop(self, node, position):
        """Whether a node dropped at ``position`` of ``node`` lands in a
        template of a QWeb view, or among the fields it loads beside."""
        parent = node if position == "inside" else node.getparent()
        if parent is None:
            return False
        return parent.tag == "templates" or studio_arch.in_template(parent)

    @api.model
    def _loaded_fields(self, arch):
        """The names of the fields a QWeb view loads outside its templates."""
        return {
            child.get("name")
            for child in studio_arch.elements(arch)
            if child.tag == "field"
        }

    def _op_add_existing_field(self, view, arch, op):
        target, position, node = self._check_drop(arch, op, view.type)
        name = op.get("field_name")
        if name not in self._studio_field_names(view.model):
            raise UserError(self.env._("Unknown field %(name)s.", name=name))
        if name in self._field_scope(arch, node, view.type):
            raise UserError(
                self.env._("The field %(name)s is already in the view.", name=name)
            )
        self._refuse(
            studio_arch.geo_refusal(
                view.type,
                self._field_info(view.model, name).get("type"),
                templated=self._in_template_drop(node, position),
            )
        )
        node_attrs = {}
        extra = {}
        if view.type == "timeline" and studio_arch.in_template(node):
            extra = self._item_field(view.model, arch, name)
        elif view.type == "search":
            if not self._field_info(view.model, name).get("searchable"):
                raise UserError(
                    self.env._("The records cannot be searched by %(name)s.", name=name)
                )
        elif view.type in studio_arch.AXIS_VIEW_TYPES:
            node_attrs = self._check_pivot_axis(
                view.model,
                name,
                op.get("axis"),
                op.get("interval"),
                axes=studio_arch.AXIS_VIEW_TYPES[view.type],
            )
        elif view.type == "kanban" and op.get("widget"):
            node_attrs["widget"] = self._clean_widget(op["widget"])
        return self._add_change(
            view,
            "add_existing_field",
            target,
            position,
            {"field_name": name, "node_attrs": node_attrs, **extra},
        )

    def _item_field(self, model, arch, name):
        """The payload keys of a field dropped into a timeline item: how it
        shows (``item``, see ``arch.item_value``), and ``load`` when the
        view does not load it yet."""
        info = self._field_info(model, name)
        if info["type"] not in studio_arch.ITEM_FIELD_TYPES:
            raise UserError(
                self.env._(
                    "A timeline item cannot show %(name)s: its type is %(type)s.",
                    name=info.get("string") or name,
                    type=info["type"],
                )
            )
        return {
            "item": studio_arch.item_kind(info["type"]),
            "load": name not in self._loaded_fields(arch),
        }

    def _op_add_filter(self, view, arch, op):
        """A <filter> with a domain built from conditions {field, operator,
        value}, joined by AND."""
        target, position, _node = self._check_drop(arch, op, view.type)
        conditions = op.get("conditions")
        if conditions is None and op.get("field"):
            conditions = [
                {
                    "field": op.get("field"),
                    "operator": op.get("operator"),
                    "value": op.get("value"),
                }
            ]
        if not conditions or not isinstance(conditions, list):
            raise UserError(self.env._("A filter needs at least one condition."))
        terms, cleaned, names, labels = [], [], [], []
        for condition in conditions:
            name = (condition or {}).get("field")
            info = self._field_info(view.model, name)
            if not info.get("searchable"):
                raise UserError(
                    self.env._("The records cannot be searched by %(name)s.", name=name)
                )
            operator = condition.get("operator") or "="
            value = condition.get("value")
            if operator in ("set", "not set"):
                value = None
            else:
                value = self._typed_value(info, value)
            try:
                terms.append(
                    studio_arch.filter_condition(name, info["type"], operator, value)
                )
            except studio_arch.ArchError as exc:
                raise UserError(self._arch_message(exc)) from exc
            cleaned.append({"field": name, "operator": operator, "value": value})
            names.append(name)
            labels.append(info.get("string") or name)
        self._check_domain(view.model, terms)
        label = (op.get("label") or "").strip() or ", ".join(labels)
        node_name = studio_arch.node_name_from_label(
            "studio_filter", label, studio_arch.arch_names(arch)
        )
        attrs = {
            "name": node_name,
            "string": label,
            "domain": studio_arch.domain_text(terms),
        }
        return self._add_change(
            view,
            "add_node",
            target,
            position,
            {
                "kind": "filter",
                "node_name": node_name,
                "node": {"tag": "filter", "attrs": attrs},
                "conditions": cleaned,
                "fields": sorted(set(names)),
            },
        )

    def _op_add_group_by(self, view, arch, op):
        """A <filter> that groups by a field, by ``interval`` for a date."""
        target, position, _node = self._check_drop(arch, op, view.type)
        name = op.get("field_name")
        info = self._check_groupable(view.model, name)
        interval = self._check_interval(info, op.get("interval"))
        group_by = f"{name}:{interval}" if interval else name
        if any(
            studio_arch.group_by_of(node) == group_by for node in arch.iter("filter")
        ):
            raise UserError(
                self.env._(
                    "The search view already groups by %(group_by)s.",
                    group_by=group_by,
                )
            )
        label = (op.get("label") or "").strip() or info.get("string") or name
        node_name = studio_arch.node_name_from_label(
            "studio_group_by",
            f"{name} {interval or ''}",
            studio_arch.arch_names(arch),
        )
        attrs = {
            "name": node_name,
            "string": label,
            "context": studio_arch.group_by_context(name, interval),
        }
        return self._add_change(
            view,
            "add_node",
            target,
            position,
            {
                "kind": "group_by",
                "node_name": node_name,
                "node": {"tag": "filter", "attrs": attrs},
                "group_by": group_by,
                "fields": [name],
            },
        )

    def _op_add_separator(self, view, arch, op):
        """A <separator>; in a form, ``label`` gives it a title."""
        target, position, _node = self._check_drop(arch, op, view.type)
        attrs = {}
        label = (op.get("label") or "").strip()
        if label and view.type == "form":
            attrs["string"] = label
        return self._add_change(
            view,
            "add_node",
            target,
            position,
            {
                "kind": "separator",
                "node": {"tag": "separator", "attrs": attrs},
            },
        )

    def _layout_label(self, op, default):
        """The label of a new group or tab: ``op["label"]``, else
        ``default``, in the user's language."""
        return (op.get("label") or "").strip() or default

    def _op_add_group(self, view, arch, op):
        """A <group> of a form, named after its label."""
        target, position, _node = self._check_drop(arch, op, view.type)
        label = self._layout_label(op, self.env._("New group"))
        name = studio_arch.node_name_from_label(
            "studio_group", label, studio_arch.arch_names(arch)
        )
        return self._add_change(
            view,
            "add_node",
            target,
            position,
            {
                "kind": "group",
                "node": {
                    "tag": "group",
                    "attrs": {"name": name, "string": label},
                },
            },
        )

    def _op_add_page(self, view, arch, op):
        """A tab of a form: a <page> inside a <notebook> or next to a
        <page>; anywhere else, a new <notebook> that holds it, where a
        notebook may go (``notebook_refusal``)."""
        target = op.get("target")
        position = op.get("position") or "after"
        node = self._locate(arch, target)
        label = self._layout_label(op, self.env._("New tab"))
        taken = studio_arch.arch_names(arch)
        page = {
            "tag": "page",
            "attrs": {
                "name": studio_arch.node_name_from_label("studio_page", label, taken),
                "string": label,
            },
        }
        if studio_arch.page_refusal(node, position) is None:
            return self._add_change(
                view,
                "add_node",
                target,
                position,
                {"kind": "page", "node": page},
            )
        target, position, node = self._check_drop(arch, op, view.type)
        self._refuse(studio_arch.notebook_refusal(node, position))
        notebook = studio_arch.node_name_from_label("studio", "notebook", taken)
        return self._add_change(
            view,
            "add_node",
            target,
            position,
            {
                "kind": "notebook",
                "node": {
                    "tag": "notebook",
                    "attrs": {"name": notebook},
                    "children": [page],
                },
            },
        )

    def _op_add_widget(self, view, arch, op):
        """A <widget> of ``WIDGETS`` in a template of the view."""
        target, position, _node = self._check_drop(arch, op, view.type)
        widget = op.get("widget")
        if widget not in studio_arch.WIDGETS:
            raise UserError(self.env._("Invalid widget %(name)s.", name=widget))
        attrs = {"name": widget}
        given = op.get("attrs") or {}
        for key in studio_arch.WIDGETS[widget]:
            value = str(given.get(key) or "").strip()
            if value:
                attrs[key] = value
        if not re.match(r"^[a-z0-9 _-]*$", attrs.get("bg_color", "")):
            raise UserError(
                self.env._("Invalid color %(color)s.", color=attrs["bg_color"])
            )
        return self._add_change(
            view,
            "add_node",
            target,
            position,
            {"kind": "widget", "node": {"tag": "widget", "attrs": attrs}},
        )

    def _op_move(self, view, arch, op):
        """Move a node; in a pivot or a graph, ``axis`` also moves a field
        to another axis."""
        target, position, node = self._check_drop(arch, op, view.type)
        source_path = op.get("source")
        source = self._locate(arch, source_path)
        self._refuse(studio_arch.move_refusal(view.type, source))
        if source.tag == "page":
            self._refuse(studio_arch.page_refusal(node, position))
        elif source.tag == "notebook" and view.type == "form":
            self._refuse(studio_arch.notebook_refusal(node, position))
        if source is node or source in node.iterancestors():
            raise UserError(self.env._("A node cannot move into itself."))
        destination = node if position == "inside" else node.getparent()
        if (
            view.type in studio_arch.TEMPLATED_TYPES
            and studio_arch.in_template(source)
            and not studio_arch.in_template(destination)
        ):
            self._refuse(
                studio_arch.ArchError(
                    "A node of a template cannot move out of the templates.",
                    "template_move",
                )
            )
        payload = {"source": source_path}
        field_name = studio_arch.shown_field_name(view.type, source)
        if field_name:
            payload["field_name"] = field_name
        elif source.get("name"):
            payload["node_name"] = source.get("name")
        axis = op.get("axis")
        if view.type in studio_arch.AXIS_VIEW_TYPES and source.tag == "field" and axis:
            if axis != source.get("type"):
                interval = None if axis == "measure" else source.get("interval")
                attrs = self._check_pivot_axis(
                    view.model,
                    source.get("name"),
                    axis,
                    interval,
                    axes=studio_arch.AXIS_VIEW_TYPES[view.type],
                )
                if axis == "measure" and source.get("interval"):
                    attrs["interval"] = ""
                payload["attrs"] = attrs
        if payload.get("attrs"):
            move = {
                "type": "move",
                "xpath": target,
                "position": position,
                "payload": payload,
            }
            try:
                payload["attrs_xpath"] = studio_arch.moved_node_xpath(
                    arch, move, view.type
                )
            except Exception as exc:  # noqa: BLE001 - reported as the move error
                raise UserError(self._arch_message(exc)) from exc
        elif op.get("merge") and not (
            view.type in studio_arch.TEMPLATED_TYPES and studio_arch.in_template(source)
        ):
            merged = self._merged_move(view, target, position, source_path)
            if merged is not None:
                return merged
        return self._add_change(view, "move", target, position, payload)

    def _merged_move(self, view, target, position, source_path):
        """Fold the move of the node at ``source_path`` to ``target`` /
        ``position`` into the last change of ``view`` when that change is a
        move of the same node without pivot attributes: the change then
        holds the one move from where the node stood before it
        (``studio_arch.merged_move``), its payload unchanged, since its
        source still names the node in the arch without it. Only the last
        change: a later change may locate a node by a position the move
        shifts. Return the change, an empty recordset when the node is
        back where it stood (the change leaves the draft), or None when
        nothing merges."""
        last = self._view_changes(view)[-1:]
        if last.change_type != "move" or last._payload().get("attrs"):
            return None
        before, errors = self._draft_arch_without(view, last)
        if errors:
            return None
        move = {
            "type": "move",
            "xpath": target,
            "position": position,
            "payload": {"source": source_path},
        }
        try:
            place = studio_arch.merged_move(before, last._as_dict(), move, view.type)
        except Exception:  # noqa: BLE001 - a move that does not merge is added
            return None
        if place is None:
            last.unlink()
            return last.browse()
        last.write({"xpath": place[0], "position": place[1]})
        return last

    def _op_hide(self, view, arch, op):
        """Hide a node: by its hide attribute, or, in a search or a pivot
        view, by removing it (see ``HIDE_MODES``)."""
        if studio_arch.hide_mode(view.type) == "remove":
            if not op.get("value"):
                raise UserError(
                    self.env._(
                        "A removed node comes back with Undo, or by deleting "
                        "the change that removed it."
                    )
                )
            return self._remove_node(view, arch, op)
        node = self._locate(arch, op.get("target"))
        self._refuse(studio_arch.hide_refusal(view.type, node))
        return self._attribute_operation(view, arch, op)

    def _added_changes(self, view, xpath):
        """The change of ``view`` that added the node at ``xpath`` of the
        draft, or an empty recordset for a node of the view itself. The
        node is found by the change that inserts it, whatever its name: a
        ribbon is named after its widget, a separator has no name."""
        changes = self._view_changes(view)
        key = studio_arch.added_key(
            self._base_arch(view), [c._as_dict() for c in changes], view.type, xpath
        )
        return changes.filtered(lambda c: str(c.id) == key)

    def _replaced_change(self, view, arch, existing, xpath):
        """The change among ``existing`` that a new value for the node at
        ``xpath`` replaces: by name or at the root, the latest one; by
        position, only the last change of the view, since a later change
        may have moved what the position names."""
        replaced = existing[-1:]
        stable = xpath.startswith("//") or xpath == f"/{arch.tag}"
        if replaced and not stable and replaced != self._view_changes(view)[-1:]:
            replaced = existing.browse()
        return replaced

    def _attribute_operation(self, view, arch, op):
        otype = op["type"]
        xpath = op.get("target")
        node = self._locate(arch, xpath)
        value = op.get("value")
        if otype in studio_arch.BOOLEAN_CHANGES:
            value = bool(value)
        elif otype == "optional":
            value = value or ""
            if value not in studio_arch.OPTIONAL_VALUES or view.type != "list":
                raise UserError(self.env._("Only a list column can be optional."))
        else:
            value = (value or "").strip()
        name = node.get("name") if node.tag == "field" else None
        own = name and self._field_add_change(view.model, name)
        field_attr = {
            "relabel": "field_description",
            "readonly": "readonly",
            "help": "help",
        }.get(otype)
        if own and field_attr:
            # A field of the project: the change goes to its definition.
            return self._update_field(
                view, {"field_name": name, "field": {field_attr: value}}
            )
        if otype == "relabel" and value and node.tag != "field":
            added = self._added_changes(view, xpath)
            if added.change_type == "add_node":
                # An element of the project: the label goes to its definition.
                payload = added._payload()
                payload["node"]["attrs"]["string"] = value
                added._set_payload(payload)
                return added
        existing = self._view_changes(view).filtered(
            lambda c: c.change_type == otype and c.xpath == xpath
        )
        replaced = self._replaced_change(view, arch, existing, xpath)
        if otype in studio_arch.BOOLEAN_CHANGES:
            if replaced:
                before, _errors = self._draft_arch_without(view, replaced)
                original = self._locate(before, xpath)
            else:
                original = node
            attribute = (
                studio_arch.hide_attribute(view.type)
                if otype == "hide"
                else studio_arch.ATTRIBUTE_CHANGES[otype]
            )
            if value == studio_arch.constant_true(original.get(attribute)):
                # The node is back to the arch without the change: a
                # condition of the view (« invisible="is_company" ») stays.
                replaced.unlink()
                return replaced.browse()
        if replaced:
            payload = replaced._payload()
            payload["value"] = value
            replaced._set_payload(payload)
            return replaced
        return self._add_change(view, otype, xpath, "attributes", {"value": value})

    def _attribute_value(self, view, node, kind, value):
        """(text, fields): the attribute text of ``value`` for an attribute
        of ``kind`` (see ``SETTABLE_ATTRIBUTES``), and the fields it names.
        An empty text removes the attribute."""
        if kind == "bool":
            if value in (None, ""):
                return "", []
            if isinstance(value, str):
                value = studio_arch.constant_true(value)
            return ("True" if value else "False"), []
        if kind == "bool_number":
            # « 1 » or no attribute: the view reads a number (number_true).
            if isinstance(value, str):
                value = studio_arch.number_true(value) or studio_arch.constant_true(
                    value
                )
            return ("1" if value else ""), []
        if kind == "colors":
            return self._colors_value(view.model, value)
        if kind == "groups":
            return self._groups_value(value), []
        if kind == "calendar_filter":
            return self._calendar_filter_value(view.model, node, value)
        if kind == "parent_field" and value in (None, "", False):
            # Without the attribute, web_hierarchy reads parent_id.
            self._check_child_follows(view.model, node, "parent_id")
            return "", []
        if value in (None, "", False):
            return "", []
        if not isinstance(value, str):
            raise UserError(self.env._("Invalid value %(value)s.", value=value))
        check = {
            "group_field": self._group_field_value,
            "relation_group_field": self._relation_group_field_value,
            "date_field": self._typed_field_value,
            "number_field": self._typed_field_value,
            "color_field": self._color_field_value,
            "bool_field": self._bool_field_value,
            "parent_field": self._parent_field_value,
            "child_field": self._child_field_value,
            "coordinate_field": self._leaflet_field_value,
            "text_field": self._leaflet_field_value,
            "image_field": self._leaflet_field_value,
            "pixels": self._leaflet_number_value,
            "offset": self._leaflet_number_value,
            "order": self._order_value,
            "axis": self._axis_value,
            "graph_axis": self._axis_value,
            "interval": self._interval_value,
            "widget": lambda model, node, kind, value: (self._clean_widget(value), []),
            "field_domain": self._field_domain_value,
            **{choice: self._choice_value for choice in studio_arch.CHOICES},
        }.get(kind)
        if not check:
            raise UserError(self.env._("Invalid value %(value)s.", value=value))
        return check(view.model, node, kind, value.strip())

    def _group_field_value(self, model, node, kind, value):
        self._check_groupable(model, value)
        return value, [value]

    def _relation_group_field_value(self, model, node, kind, value):
        info = self._check_groupable(model, value)
        if info["type"] not in studio_arch.RELATION_TYPES:
            raise UserError(
                self.env._(
                    "A timeline groups its items by a many2one or a many2many "
                    "field only, not by %(name)s.",
                    name=value,
                )
            )
        return value, [value]

    def _typed_field_value(self, model, node, kind, value):
        info = self._field_info(model, value)
        types = studio_arch.DATE_TYPES if kind == "date_field" else ("integer", "float")
        if info["type"] not in types or not info.get("store"):
            raise UserError(
                self.env._(
                    "%(name)s does not fit this attribute: a stored %(types)s "
                    "field is needed.",
                    name=value,
                    types=" / ".join(types),
                )
            )
        return value, [value]

    def _color_field_value(self, model, node, kind, value):
        """The field ``value`` the « color » of a calendar reads: a stored
        field of a type of ``CALENDAR_COLOR_TYPES``."""
        info = self._field_info(model, value)
        types = studio_arch.CALENDAR_COLOR_TYPES
        if info["type"] not in types or not info.get("store"):
            raise UserError(
                self.env._(
                    "%(name)s does not fit this attribute: a stored %(types)s "
                    "field is needed.",
                    name=value,
                    types=" / ".join(types),
                )
            )
        return value, [value]

    def _bool_field_value(self, model, node, kind, value):
        """The field ``value`` the « all_day » of a calendar reads: a stored
        boolean."""
        info = self._field_info(model, value)
        if info["type"] != "boolean" or not info.get("store"):
            raise UserError(
                self.env._(
                    "%(name)s does not fit this attribute: a stored %(types)s "
                    "field is needed.",
                    name=value,
                    types="boolean",
                )
            )
        return value, [value]

    def _leaflet_field_value(self, model, node, kind, value):
        """The field ``value`` a root attribute of a map of ``kind`` names:
        a stored float for a coordinate (the map compares it), a char, a
        text or a selection for a popup title or address (searchRead reads
        a computed field too; a many2one would print as [id, name]), a
        binary for a marker image, which /web/image serves."""
        info = self._field_info(model, value)
        types = {
            "coordinate_field": ("float",),
            "text_field": studio_arch.LEAFLET_TEXT_TYPES,
            "image_field": ("binary",),
        }[kind]
        if kind == "coordinate_field" and (
            info["type"] not in types or not info.get("store")
        ):
            raise UserError(
                self.env._(
                    "%(name)s does not fit this attribute: a stored %(types)s "
                    "field is needed.",
                    name=value,
                    types=" / ".join(types),
                )
            )
        if info["type"] not in types:
            raise UserError(
                self.env._(
                    "%(name)s does not fit this attribute: a %(types)s field "
                    "is needed.",
                    name=value,
                    types=" / ".join(types),
                )
            )
        return value, [value]

    def _leaflet_number_value(self, model, node, kind, value):
        """The integer text of ``value`` for a marker size (``pixels``,
        LEAFLET_PIXELS) or a popup anchor offset (``offset``,
        LEAFLET_OFFSET) of a map."""
        low, high = (
            studio_arch.LEAFLET_PIXELS
            if kind == "pixels"
            else studio_arch.LEAFLET_OFFSET
        )
        try:
            number = int(value)
        except ValueError:
            number = None
        if number is None or not low <= number <= high:
            raise UserError(
                self.env._(
                    "%(value)s is not a whole number from %(low)s to %(high)s.",
                    value=value,
                    low=low,
                    high=high,
                )
            )
        return str(number), []

    def _parent_field_value(self, model, node, kind, value):
        """The « parent_field » ``value`` of a hierarchy: a stored many2one
        of ``model`` to itself, which the « child_field » of ``node``, when
        set, has for inverse; web_hierarchy builds its tree from both."""
        info = self._field_info(model, value)
        if (
            info["type"] != "many2one"
            or info.get("relation") != model
            or not info.get("store")
        ):
            raise UserError(
                self.env._(
                    "The parent of a hierarchy is a stored many2one from "
                    "%(model)s to itself, not %(name)s.",
                    model=model,
                    name=info.get("string") or value,
                )
            )
        self._check_child_follows(model, node, value)
        return value, [value]

    def _check_child_follows(self, model, node, parent):
        """UserError when the « child_field » of the hierarchy ``node`` is
        the inverse of another field than ``parent``: the children would
        follow one field and the parents another."""
        child = node.get("child_field")
        if not child or model not in self.env:
            return
        field = self.env[model]._fields.get(child)
        if field is None or getattr(field, "inverse_name", None) != parent:
            raise UserError(
                self.env._(
                    "Remove the children field first: it follows another "
                    "parent field."
                )
            )

    def _child_field_value(self, model, node, kind, value):
        """The « child_field » ``value`` of a hierarchy: a one2many of
        ``model`` to itself whose inverse is the parent field of ``node``
        (« parent_field », parent_id without it)."""
        info = self._field_info(model, value)
        parent = node.get("parent_field") or "parent_id"
        field = self.env[model]._fields.get(value) if model in self.env else None
        if (
            info["type"] != "one2many"
            or info.get("relation") != model
            or getattr(field, "inverse_name", None) != parent
        ):
            raise UserError(
                self.env._(
                    "The children of a hierarchy are the one2many of %(model)s "
                    "whose inverse is %(parent)s, not %(name)s.",
                    model=model,
                    parent=parent,
                    name=info.get("string") or value,
                )
            )
        return value, [value]

    def _calendar_filter_value(self, model, node, value):
        """(text, fields) of the « filters » of a calendar field: « True »
        for a true ``value``, else an empty text, which removes the
        attribute; the calendar reads « False » as a filter too. The field
        is a many2one or a many2many (``CALENDAR_FILTER_TYPES``)."""
        if isinstance(value, str):
            value = studio_arch.constant_true(value)
        if not value:
            return "", []
        if node.tag != "field":
            raise UserError(self.env._("Invalid value %(value)s.", value=value))
        info = self._field_info(model, node.get("name"))
        if info["type"] not in studio_arch.CALENDAR_FILTER_TYPES:
            raise UserError(
                self.env._(
                    "The side panel of a calendar filters by a many2one or a "
                    "many2many field only, not by %(name)s.",
                    name=info.get("string") or node.get("name"),
                )
            )
        return "True", []

    def _order_value(self, model, node, kind, value):
        try:
            names = studio_arch.order_fields(value)
        except studio_arch.ArchError as exc:
            raise UserError(self._arch_message(exc)) from exc
        for name in names:
            if not self._field_info(model, name).get("sortable"):
                raise UserError(
                    self.env._("The records cannot be sorted by %(name)s.", name=name)
                )
        return value, sorted(set(names))

    def _axis_value(self, model, node, kind, value):
        """The axis ``value`` of a pivot field (kind « axis ») or of a graph
        field (« graph_axis »)."""
        interval = node.get("interval")
        if value == "measure" and interval:
            raise UserError(
                self.env._("A measure takes no interval: remove the interval first.")
            )
        axes = (
            studio_arch.GRAPH_AXES if kind == "graph_axis" else studio_arch.PIVOT_AXES
        )
        self._check_pivot_axis(model, node.get("name"), value, interval, axes=axes)
        return value, []

    def _interval_value(self, model, node, kind, value):
        if node.get("type") == "measure":
            raise UserError(self.env._("A measure takes no interval."))
        info = self._field_info(model, node.get("name"))
        return self._check_interval(info, value), []

    def _domain_comodel(self, model, name):
        """The comodel of the relational field ``name`` of ``model``, the
        model its domain searches. UserError when the field is not
        relational, or while its comodel is a model of the project not
        created yet: a domain is checked by a search. A new field of the
        project on an existing model is read from its definition."""
        change = (
            self._field_add_change(model, name)
            if not self._studio_pending_line(model)
            and name not in self.env[model]._fields
            else None
        )
        if change:
            definition = change._payload().get("field") or {}
            info = {
                "type": definition.get("ttype"),
                "relation": definition.get("relation"),
                "string": definition.get("field_description"),
            }
        else:
            info = self._field_info(model, name)
        if info["type"] not in studio_arch.RELATIONAL_TYPES:
            raise UserError(
                self.env._(
                    "Only a relational field takes a domain, not %(name)s.",
                    name=info.get("string") or name,
                )
            )
        comodel = info.get("relation") or ""
        if comodel not in self.env:
            raise UserError(
                self.env._("Apply the model %(model)s first.", model=comodel)
            )
        return comodel

    @api.model
    def _parse_field_domain(self, value):
        """The list of terms of the domain text ``value``, a Python literal:
        a domain that reads the record (« uid », a field of the form) is
        refused, the generated module writes it as it stands."""
        try:
            domain = ast.literal_eval(value)
            if not isinstance(domain, (list, tuple)):
                raise ValueError(value)
            check_domain_shape(domain)
        except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
            raise UserError(
                self.env._(
                    "%(value)s is not a domain: a list of terms (field, "
                    "operator, value) with fixed values is needed.",
                    value=value,
                )
            ) from None
        return [tuple(term) if isinstance(term, list) else term for term in domain]

    def _field_domain_value(self, model, node, kind, value):
        """The domain of a relational field, written as ``repr`` writes the
        list of its terms; checked by a search of the comodel."""
        comodel = self._domain_comodel(model, node.get("name"))
        domain = self._parse_field_domain(value)
        try:
            with self.env.cr.savepoint():
                self.env[comodel].sudo()._search(domain)
        except (ValueError, KeyError, TypeError) as exc:
            raise UserError(
                self.env._("The domain does not apply: %(error)s", error=exc)
            ) from exc
        return repr(list(domain)), []

    def _field_options_value(self, model, node, value, option_fields):
        """(text, record fields, extra) for the ``options`` of the field
        ``node`` of ``model``. ``value`` is a dictionary or a text of fixed
        values (see ``studio_arch.parse_field_options``). ``option_fields``
        maps an option to the model whose field it names: « record » (the
        model of the view, as « currency_field ») or « comodel » (the model
        the field points to, as « color_field » of many2many_tags). Each
        field named must exist: the record fields go to ``fields``, the
        comodel fields to ``extra`` (``option_model``, ``option_fields``)
        for the dependencies of the generated module."""
        try:
            options = studio_arch.parse_field_options(
                value if value not in (None, False) else ""
            )
        except studio_arch.ArchError:
            raise UserError(
                self.env._(
                    "%(value)s is not a set of options: a dictionary of fixed "
                    "values is needed.",
                    value=value,
                )
            ) from None
        if not isinstance(option_fields, dict) or not all(
            isinstance(key, str) and scope in ("record", "comodel")
            for key, scope in option_fields.items()
        ):
            raise UserError(self.env._("Invalid value %(value)s.", value=option_fields))
        record_names, comodel, comodel_names = set(), None, set()
        for option, scope in option_fields.items():
            name = options.get(option)
            if not isinstance(name, str) or not name:
                continue
            if scope == "record":
                if self._studio_pending_line(model):
                    raise UserError(
                        self.env._(
                            "Apply the model first: an option names a field "
                            "created already."
                        )
                    )
                self._field_info(model, name)
                record_names.add(name)
            else:
                comodel = comodel or self._domain_comodel(model, node.get("name"))
                if name not in self.env[comodel]._fields:
                    raise UserError(self.env._("Unknown field %(name)s.", name=name))
                comodel_names.add(name)
        extra = {}
        if comodel_names:
            extra = {"option_model": comodel, "option_fields": sorted(comodel_names)}
        return studio_arch.options_text(options), sorted(record_names), extra

    @api.model
    def _groups_list(self, value):
        """[external ids] of a ``groups`` value: a list, or a text of ids
        separated by commas; empty entries are dropped."""
        if value in (None, "", False):
            return []
        if isinstance(value, str):
            value = value.split(",")
        if not isinstance(value, (list, tuple)) or not all(
            isinstance(item, str) for item in value
        ):
            raise UserError(self.env._("Invalid value %(value)s.", value=value))
        return [item.strip() for item in value if item.strip()]

    def _groups_value(self, value):
        """The ``groups`` text of the external ids ``value``. Each one names
        a group the generated module can name: one under an installed
        module, or a group of the project Apply created. A leading « ! »
        (not in the group) stays."""
        result = []
        for item in self._groups_list(value):
            xmlid = item[1:] if item.startswith("!") else item
            line = self.group_line_ids.filtered(
                lambda g, x=xmlid: g._studio_full_xmlid() == x
            )
            if line:
                if not line._studio_group_record():
                    raise UserError(
                        self.env._(
                            "Apply the group %(group)s first: the view names "
                            "it by its external id.",
                            group=line.name,
                        )
                    )
            else:
                group = self.env.ref(xmlid, raise_if_not_found=False)
                module = xmlid.split(".", 1)[0] if "." in xmlid else ""
                installed = (
                    self.env["ir.module.module"]
                    .sudo()
                    .search_count(
                        [
                            ("name", "=", module),
                            ("state", "in", ("installed", "to upgrade")),
                        ]
                    )
                )
                if group is None or group._name != "res.groups" or not installed:
                    raise UserError(
                        self.env._(
                            "%(group)s is not the external id of a group of an "
                            "installed module nor of an applied group of the "
                            "project.",
                            group=xmlid,
                        )
                    )
            if item not in result:
                result.append(item)
        return ",".join(result)

    def _choice_value(self, model, node, kind, value):
        """``value`` of an attribute of a kind of ``CHOICES``: one of its
        values."""
        if value not in studio_arch.CHOICES[kind]:
            raise UserError(self.env._("Invalid value %(value)s.", value=value))
        return value, []

    def _colors_value(self, model, rules):
        """The ``colors`` text of a timeline from rules {color, field,
        operator, value}."""
        if rules in (None, "", False, []):
            return "", []
        if not isinstance(rules, list):
            raise UserError(self.env._("Invalid value %(value)s.", value=rules))
        typed = []
        for rule in rules:
            rule = dict(rule or {})
            info = self._field_info(model, rule.get("field"))
            if info["type"] not in studio_arch.COLOR_FIELD_TYPES:
                raise UserError(
                    self.env._(
                        "A color rule cannot compare %(name)s, a %(type)s field.",
                        name=info.get("string") or rule.get("field"),
                        type=info["type"],
                    )
                )
            rule["value"] = self._typed_value(info, rule.get("value"))
            typed.append(rule)
        try:
            text = studio_arch.colors_text(typed)
        except studio_arch.ArchError as exc:
            raise UserError(self._arch_message(exc)) from exc
        return text, sorted({rule["field"] for rule in typed})

    @api.model
    def _normal_attribute(self, kind, text):
        """``text``, the attribute of a node, as ``_attribute_value`` would
        write it, to tell whether a value brings the node back."""
        if text is None:
            return ""
        if kind == "calendar_filter":
            # The calendar tests « filters » by its presence.
            return "True"
        if kind == "bool":
            if studio_arch.constant_true(text):
                return "True"
            if text in ("0", "False", "false"):
                return "False"
        if kind == "bool_number":
            return "1" if studio_arch.number_true(text) else ""
        if kind == "groups":
            return ",".join(item.strip() for item in text.split(",") if item.strip())
        if kind == "field_options":
            try:
                return studio_arch.options_text(studio_arch.parse_field_options(text))
            except studio_arch.ArchError:
                # An expression stays as the arch writes it.
                return text
        if kind == "field_domain":
            try:
                return repr(
                    [
                        tuple(t) if isinstance(t, list) else t
                        for t in ast.literal_eval(text)
                    ]
                )
            except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
                return text
        return text

    def _op_set_attribute(self, view, arch, op):
        """Set an attribute of ``SETTABLE_ATTRIBUTES`` on a node. A value
        that brings the node back to the arch without the change removes
        the change."""
        xpath = op.get("target")
        node = self._locate(arch, xpath)
        attribute = op.get("attribute")
        settable = studio_arch.SETTABLE_ATTRIBUTES.get(view.type, {})
        kind = settable.get(node.tag, {}).get(attribute)
        if node.tag == view.type and node.getparent() is not None:
            kind = None
        if node.tag == "field" and any(
            parent.tag == "field" for parent in node.iterancestors()
        ):
            # A field of the sub-view of an x2many belongs to its comodel.
            kind = None
        if not kind:
            raise UserError(
                self.env._(
                    "The attribute %(attribute)s of <%(tag)s> cannot be set here.",
                    attribute=attribute,
                    tag=node.tag,
                )
            )
        extra = {}
        if kind == "field_options":
            value, named, extra = self._field_options_value(
                view.model, node, op.get("value"), op.get("option_fields") or {}
            )
        else:
            value, named = self._attribute_value(view, node, kind, op.get("value"))
        required = studio_arch.REQUIRED_ATTRIBUTES.get((view.type, node.tag), ())
        if not value and attribute in required:
            raise UserError(
                self.env._(
                    "The view needs the attribute %(attribute)s.", attribute=attribute
                )
            )
        existing = self._view_changes(view).filtered(
            lambda c: c.change_type == "set_attribute"
            and c.xpath == xpath
            and c._payload().get("attribute") == attribute
        )
        replaced = self._replaced_change(view, arch, existing, xpath)
        base = arch
        if replaced:
            base, _errors = self._draft_arch_without(view, replaced)
            original = self._locate(base, xpath).get(attribute)
        else:
            original = node.get(attribute)
        if value == self._normal_attribute(kind, original):
            replaced.unlink()
            return replaced.browse()
        payload = {"attribute": attribute, "value": value, "fields": named, **extra}
        if kind in ("parent_field", "child_field") and value:
            if value not in self._loaded_fields(base):
                # The change loads the field beside its templates.
                payload["load"] = [value]
        if kind == "groups":
            # The external ids the generation depends on and a removal of a
            # group of the project checks.
            payload["groups"] = [x.lstrip("!") for x in value.split(",") if x]
        elif kind == "field_domain" and value:
            payload["domain_model"] = self._domain_comodel(view.model, node.get("name"))
            payload["domain_fields"] = sorted(
                {
                    term[0].split(".", 1)[0]
                    for term in ast.literal_eval(value)
                    if isinstance(term, tuple) and isinstance(term[0], str)
                }
            )
        if replaced:
            replaced._set_payload(payload)
            return replaced
        return self._add_change(view, "set_attribute", xpath, "attributes", payload)

    def _update_field(self, view, op):
        """A new definition of a new field of the project; its technical
        name stays. A new label of a field not created yet renames it after
        the label while its name is proposed (``name_auto``, missing on a
        field drafted before it, counts as proposed); a rename refused
        keeps the name. Its options (FIELD_OPTIONS) change until Apply
        creates it; UserError after. Its type stays, except the shape of a
        geometry field, another of GEO_TYPES until Apply: the column of
        PostGIS holds one shape."""
        name = op.get("field_name")
        change = self._field_add_change(view.model, name)
        if not change:
            raise UserError(
                self.env._("%(name)s is not a field of this project.", name=name)
            )
        payload = change._payload()
        definition = dict(payload.get("field") or {}, **(op.get("field") or {}))
        old_type = payload["field"].get("ttype")
        if definition.get("ttype") != old_type:
            geo = studio_arch.GEO_TYPES
            if old_type not in geo or definition.get("ttype") not in geo:
                raise UserError(self.env._("The type of a field cannot change."))
            if self._studio_field_applied(view.model, name):
                raise UserError(
                    self.env._(
                        "The field %(name)s exists: its shape is set before "
                        "Apply only.",
                        name=name,
                    )
                )
        if self._studio_options_changed(
            payload["field"], op.get("field") or {}
        ) and self._studio_field_applied(view.model, name):
            # Translatable converts the column to jsonb, and Odoo widens a
            # varchar but never narrows it: a smaller size would leave the
            # column and the field apart. The options stay those of the
            # column as Apply created it.
            raise UserError(
                self.env._(
                    "The field %(name)s exists: whether it is translatable, "
                    "indexed and its maximum size are set before Apply only.",
                    name=name,
                )
            )
        _name, definition = self._clean_field_definition(
            view.model, definition, name=name, existing=payload["field"]
        )
        payload["field"] = definition
        change._set_payload(payload)
        if (
            "field_description" in (op.get("field") or {})
            and payload.get("name_auto", True)
            and not self._studio_field_applied(view.model, name)
        ):
            try:
                self._studio_rename_field(view, {"field_name": name, "auto": True})
            except UserError:
                _logger.debug("%s keeps its name %s", view.model, name)
        return change

    @api.model
    def _studio_options_changed(self, definition, values):
        """Whether ``values``, new values of the definition ``definition``,
        change one of its options (FIELD_OPTIONS): a false or empty value
        is the same as no option."""

        def value(key, raw):
            if key != "size":
                return bool(raw)
            try:
                return int(raw or 0)
            except (TypeError, ValueError):
                return raw

        return any(
            value(key, values[key]) != value(key, definition.get(key))
            for key in FIELD_OPTIONS
            if key in values
        )

    def _studio_field_applied(self, model, name):
        """Whether the field ``name`` of ``model`` is in the database."""
        Model = self.env.get(model)
        return bool(
            (Model is not None and name in Model._fields)
            or self.env["ir.model.fields"].sudo()._get(model, name)
        )

    def _studio_rename_field(self, view, op):
        """Rename the new field ``op["field_name"]`` of the project on the
        model of ``view``, not created yet: to ``op["new_name"]``, or, with
        ``op["auto"]``, to the name its label proposes, which it then
        follows again. The changes of the project that name it follow
        (``_studio_rewrite_field_name``). UserError when the field is in the
        database (the name is a column of its table), when it is the
        LEAFLET_DATE_FIELD a map creates (the renderer reads that name),
        when the new name does not apply, or while a change, a rule or an
        added view still names the old one; nothing changes then. An inverse
        field the project
        creates on the model is renamed in the definition of the field that
        creates it (``_studio_rename_inverse``)."""
        self.ensure_one()
        model = view.model
        old = op.get("field_name")
        change = self._field_add_change(model, old)
        if not change:
            owner = self._studio_inverse_owner(model, old)
            if owner:
                return self._studio_rename_inverse(owner, model, old, op)
            raise UserError(
                self.env._("%(name)s is not a field of this project.", name=old)
            )
        if self._studio_field_applied(model, old):
            raise UserError(
                self.env._(
                    "The technical name of %(name)s cannot change once applied: "
                    "it is a column of the table.",
                    name=old,
                )
            )
        if old == studio_arch.LEAFLET_DATE_FIELD and change.view_type == "leaflet_map":
            raise UserError(
                self.env._(
                    "The map reads %(name)s by this name: the field it creates "
                    "keeps it.",
                    name=old,
                )
            )
        auto = bool(op.get("auto"))
        payload = change._payload()
        if auto:
            label = (payload.get("field") or {}).get("field_description") or ""
            new = studio_arch.field_name_from_label(
                label, self._taken_field_names(model) - {old}
            )
        else:
            new = (op.get("new_name") or "").strip()
        if new == old:
            if payload.get("name_auto", True) != auto:
                payload["name_auto"] = auto
                change._set_payload(payload)
            return change
        problem = self._studio_field_name_problem(model, new, own=old)
        if problem:
            raise UserError(problem["message"])
        with self.env.cr.savepoint():
            self._studio_rewrite_field_name(change, old, new, auto)
            self._studio_check_field_renamed(model, old)
        return change

    def _studio_rename_inverse(self, owner, model, old, op):
        """Rename the inverse field ``old`` of ``model`` that the add_field
        ``owner`` creates: to ``op["new_name"]``, or, with ``op["auto"]``, to
        the name its label proposes. The definition of ``owner`` takes the
        new name (``inverse_new`` and the ``relation_field`` of a one2many,
        ``inverse_o2m`` of a many2one), the changes of the project that name
        it follow; same refusals as ``_studio_rename_field``."""
        if self._studio_field_applied(model, old):
            raise UserError(
                self.env._(
                    "The technical name of %(name)s cannot change once applied: "
                    "it is a column of the table.",
                    name=old,
                )
            )
        payload = owner._payload()
        definition = payload.get("field") or {}
        key = "inverse_o2m" if definition.get("ttype") == "many2one" else "inverse_new"
        if op.get("auto"):
            label = definition[key].get("field_description") or ""
            taken = self._taken_field_names(model) - {old}
            if key == "inverse_o2m":
                new = self._studio_inverse_o2m_name(label, taken)
            else:
                new = studio_arch.field_name_from_label(label, taken)
        else:
            new = (op.get("new_name") or "").strip()
        if new == old:
            return owner
        problem = self._studio_field_name_problem(model, new, own=old)
        if problem:
            raise UserError(problem["message"])
        if owner.model == model and new == owner.field_name:
            raise UserError(self.env._("The field %(name)s already exists.", name=new))
        with self.env.cr.savepoint():
            self._studio_rewrite_field_refs(model, old, new, owner)
            definition[key]["name"] = new
            if key == "inverse_new":
                definition["relation_field"] = new
            owner._set_payload(payload)
            self._studio_check_field_renamed(model, old)
        return owner

    @api.model
    def _studio_rename_token(self, text, old, new):
        """``text`` (an XPath) with each « [@name='old'] » made
        « [@name='new'] »; a longer name that starts with ``old`` stays."""
        if not text:
            return text
        pattern = rf"\[@name=(['\"]){re.escape(old)}\1\]"
        return re.sub(pattern, lambda m: f"[@name={m[1]}{new}{m[1]}]", text)

    def _studio_rewrite_field_name(self, change, old, new, auto):
        """Give the new field of the add_field ``change`` the name ``new``
        instead of ``old``: its own payload (``name_auto`` = ``auto``; the
        relation table and columns of a many2many follow the name), the
        XPaths, move sources, ``field_name`` and ``fields`` of the changes of
        the project on its model, and the one2many of the project whose
        inverse it is (``_studio_rewrite_field_refs``)."""
        self.ensure_one()
        model = change.model
        self._studio_rewrite_field_refs(model, old, new, change)
        payload = change._payload()
        payload["field_name"] = new
        payload["name_auto"] = auto
        definition = payload.get("field") or {}
        if definition.get("inverse_o2m"):
            definition["inverse_o2m"]["relation_field"] = new
        if definition.get("ttype") == "many2many":
            table, column1, column2 = studio_arch.many2many_names(
                self.module_name,
                model,
                definition["relation"],
                new,
                self._studio_relation_table_names()
                - {definition.get("relation_table")},
            )
            definition.update(
                {"relation_table": table, "column1": column1, "column2": column2}
            )
        change._set_payload(payload)

    def _studio_rewrite_field_refs(self, model, old, new, change):
        """Make the field ``old`` of ``model`` ``new`` in the changes of the
        project other than ``change``: the XPaths, move sources,
        ``field_name`` and ``fields`` of the changes on ``model``, and the
        ``relation_field`` of the one2many whose existing inverse it is."""
        for other in self.change_ids.filtered(lambda c: c.model == model) - change:
            payload = other._payload()
            vals = {}
            xpath = self._studio_rename_token(other.xpath, old, new)
            if xpath != other.xpath:
                vals["xpath"] = xpath
            touched = False
            if payload.get("source"):
                source = self._studio_rename_token(payload["source"], old, new)
                touched = source != payload["source"]
                payload["source"] = source
            if payload.get("field_name") == old:
                payload["field_name"] = new
                touched = True
            if isinstance(payload.get("fields"), list) and old in payload["fields"]:
                payload["fields"] = [new if f == old else f for f in payload["fields"]]
                touched = True
            if touched:
                vals["payload"] = json.dumps(payload, sort_keys=True)
            if vals:
                other.write(vals)
        for other in self._project_field_changes() - change:
            payload = other._payload()
            definition = payload.get("field") or {}
            if (
                definition.get("ttype") == "one2many"
                and definition.get("relation") == model
                and definition.get("relation_field") == old
                and not definition.get("inverse_new")
            ):
                definition["relation_field"] = new
                other._set_payload(payload)

    def _studio_check_field_renamed(self, model, old):
        """Raise UserError while a change of the project on ``model``, one of
        its rules or a view it adds on ``model`` still names the field
        ``old`` once renamed: a name in a domain, a value or an attribute
        that the rename does not rewrite."""
        self.ensure_one()
        names = {old}
        found = False
        for change in self.change_ids.filtered(lambda c: c.model == model):
            if self._studio_change_names(change, names):
                found = change.summary
                break
        word = re.compile(rf"(?<!\w){re.escape(old)}(?!\w)")
        for rule in self.rule_line_ids:
            if found:
                break
            if (rule.model == model and word.search(rule.domain_force or "")) or (
                (model, old)
                in self._studio_domain_fields(rule.model, rule.domain_force)
            ):
                found = rule.name
        for line in self.view_line_ids.filtered(lambda v: v.model == model):
            if found:
                break
            if word.search(line.arch or ""):
                found = line._studio_view_name()
        if found:
            raise UserError(
                self.env._(
                    "%(name)s is still named by « %(change)s »: remove that "
                    "change first, or keep the name.",
                    name=old,
                    change=found,
                )
            )

    def _remove_node(self, view, arch, op):
        """Remove a node: one the project added leaves the project with the
        changes that name it; any other node is hidden, or removed from
        the arch in a view type whose hide mode is « remove »."""
        xpath = op.get("target")
        node = self._locate(arch, xpath)
        if node.getparent() is None:
            raise UserError(self.env._("The view itself cannot be removed."))
        added = self._added_changes(view, xpath)
        if node.tag == "page":
            notebook_xpath = studio_arch.node_xpath(arch, node.getparent())
            if added:
                self._remove_added_node(view, added)
                return self._remove_empty_notebook(view, notebook_xpath, added.browse())
            touched = self._remove_added_page(view, arch, node)
            if touched is not None:
                return self._remove_empty_notebook(view, notebook_xpath, touched)
        if added:
            self._remove_added_node(view, added)
            return added.browse()
        if studio_arch.hide_mode(view.type) == "remove":
            payload = {}
            field_name = studio_arch.shown_field_name(view.type, node)
            if field_name:
                payload["field_name"] = field_name
            elif node.get("name"):
                payload["node_name"] = node.get("name")
            return self._add_change(view, "remove", xpath, "replace", payload)
        self._refuse(studio_arch.hide_refusal(view.type, node))
        return self._attribute_operation(
            view, arch, {"type": "hide", "target": xpath, "value": True}
        )

    def _remove_added_node(self, view, added):
        """Remove the change ``added`` of ``view``, which adds a node, with
        the changes on that node or inside it."""
        changes = self._view_changes(view)
        keys = studio_arch.changes_on_added(
            self._base_arch(view),
            [c._as_dict() for c in changes],
            view.type,
            added.id,
        )
        removed = added | changes.filtered(lambda c: c.id in keys)
        self._studio_check_inverse_removal(removed)
        self._studio_inverse_dependents(removed).unlink()

    def _remove_added_page(self, view, arch, page):
        """Take ``page``, a tab the change that added its notebook holds
        (``NODE_CHILDREN``), out of that change, with the changes on the tab
        or inside it. Return the change of the notebook, or None when no
        change of the project added the tab."""
        notebook_xpath = studio_arch.node_xpath(arch, page.getparent())
        added = self._added_changes(view, notebook_xpath)
        if not added or added.change_type != "add_node":
            return None
        payload = added._payload()
        node_def = payload.get("node") or {}
        name = page.get("name")

        def named(child):
            return bool(name) and (child.get("attrs") or {}).get("name") == name

        children = node_def.get("children") or []
        if not any(named(child) for child in children):
            return None
        changes = self._view_changes(view)
        keys = studio_arch.changes_on_added(
            self._base_arch(view),
            [c._as_dict() for c in changes],
            view.type,
            added.id,
            child=name,
        )
        inner = changes.filtered(lambda c: c.id in keys)
        self._studio_check_inverse_removal(inner)
        self._studio_inverse_dependents(inner).unlink()
        node_def["children"] = [child for child in children if not named(child)]
        added._set_payload(payload)
        return added

    def _remove_empty_notebook(self, view, notebook_xpath, touched):
        """Remove the notebook at ``notebook_xpath`` of the draft of
        ``view`` when the project added it and it holds no tab any more;
        return ``touched``, or an empty recordset once the notebook left."""
        arch, _errors = self._draft_arch(view)
        try:
            notebook = studio_arch.locate(arch, notebook_xpath)
        except studio_arch.ArchError:
            return touched
        if any(node.tag == "page" for node in studio_arch.elements(notebook)):
            return touched
        added = self._added_changes(view, notebook_xpath)
        if not added:
            return touched
        self._remove_added_node(view, added)
        return added.browse()

    def _studio_dependent_changes(self, changes):
        """``changes`` (of this project) with every change of the project
        that locates a node one of them adds, or a node inside one, and so
        on: what ``_remove_node`` removes with an added node."""
        self.ensure_one()
        result = changes
        todo = changes
        while todo:
            found = self.env["erplibre.studio.change"]
            for view in {self._change_view(change) for change in todo}:
                view_changes = self._view_changes(view)
                dicts = [c._as_dict() for c in view_changes]
                base = self._base_arch(view)
                for change in todo & view_changes:
                    keys = studio_arch.changes_on_added(
                        base, dicts, view.type, change.id
                    )
                    found |= view_changes.filtered(lambda c, k=keys: c.id in k)
            todo = found - result
            result |= found
        return result

    def _studio_changes_of_fields(self, names):
        """The changes of the project that add or name one of the fields
        ``names`` ({model: field names}), with the changes that depend on
        the nodes they add."""
        self.ensure_one()
        naming = self.change_ids.filtered(
            lambda c: self._studio_change_names(c, names.get(c.model, ()))
        )
        return self._studio_dependent_changes(naming)

    def _studio_change_removal(self, changes):
        """``changes`` (of this project) with every change that leaves the
        draft with them, sorted in the order they apply, until none is
        added: on each view, the later changes that no longer act on the
        same node (``arch.dependent_changes``: a node a removed change adds,
        a positional XPath that would find another node); the changes that
        name a field a removed « add_field » creates
        (``_studio_changes_of_fields``, which matches the name in the XPath
        and the parameters, so a change that only mentions it goes too);
        the changes that show an inverse a removed one2many creates
        (``_studio_inverse_dependents``). A read: nothing is removed."""
        self.ensure_one()
        result = changes
        todo = changes
        while todo:
            found = self.env["erplibre.studio.change"]
            for view in {self._change_view(change) for change in todo}:
                view_changes = self._view_changes(view)
                keys = studio_arch.dependent_changes(
                    self._base_arch(view),
                    [c._as_dict() for c in view_changes],
                    view.type,
                    set((result & view_changes).ids),
                )
                found |= view_changes.filtered(lambda c, k=keys: c.id in k)
            names = {}
            for change in todo.filtered(
                lambda c: c.change_type == "add_field" and c.field_name
            ):
                names.setdefault(change.model, set()).add(change.field_name)
            if names:
                found |= self._studio_changes_of_fields(names)
            found |= self._studio_inverse_dependents(todo)
            todo = found - result
            result |= found
        return result.sorted(lambda c: (c.sequence, c.id))

    def _studio_remove_changes(self, changes):
        """Remove ``changes`` (of this project) from the draft with the
        changes of ``_studio_change_removal``; UserError, and nothing
        removed, when one is a one2many whose inverse another one2many of
        the project takes (``_studio_check_inverse_removal``). Return the
        ids of the removed changes."""
        self.ensure_one()
        project = self._editing()
        removed = project._studio_change_removal(changes.with_env(project.env))
        project._studio_check_inverse_removal(removed)
        ids = removed.ids
        removed.unlink()
        project._touch()
        return ids

    def action_undo(self, view=None):
        """Remove the last change (of ``view`` when given); a one2many goes
        with the changes that show the inverse it creates
        (``_studio_inverse_dependents``)."""
        self._check_studio_access()
        for project in self._editing():
            changes = project._view_changes(view) if view else project.change_ids
            last = changes.sorted(lambda c: (c.sequence, c.id))[-1:]
            project._studio_check_inverse_removal(last)
            project._studio_inverse_dependents(last).unlink()
            project._touch()
        return True

    def action_discard(self):
        """Back to the draft of the last Apply: its changes, apps, groups,
        models, access rows and rules; no Apply: nothing. The database is
        left as it is. A line of the snapshot that no longer applies (its
        model, menu, group or view left the database since) is left out; a
        rule or a group that lost an existing group keeps the others, and
        the editor flags what it lost. Return True, or a notification that
        lists what was left out."""
        self._check_studio_access()
        skipped = []
        for project in self._editing():
            snapshot = project._studio_load_snapshot(project.applied_snapshot)
            project.change_ids.unlink()
            project.rule_line_ids.unlink()
            project.access_line_ids.unlink()
            project.view_line_ids.unlink()
            project.new_model_ids.unlink()
            project.group_line_ids.unlink()
            project.app_ids.unlink()
            restore = project.with_context(**{RESTORE_KEY: SERVER_VALUES})
            for kind, model in (
                ("apps", "erplibre.studio.app"),
                ("groups", "erplibre.studio.group"),
                ("models", "erplibre.studio.model"),
                ("access", "erplibre.studio.access"),
                ("rules", "erplibre.studio.rule"),
                ("views", "erplibre.studio.view"),
            ):
                Line = restore.env[model]
                for item in snapshot[kind]:
                    vals = dict(
                        Line._studio_line_vals(item, project), project_id=project.id
                    )
                    skipped += project._studio_restore(Line, vals, item)
            Group = restore.env["erplibre.studio.group"]
            for item in snapshot["groups"]:
                Group._studio_restore_implied(project, item)
            project._studio_restore_company_rules(snapshot["models"])
            Change = project.env["erplibre.studio.change"]
            View = self.env["ir.ui.view"].sudo()
            for index, item in enumerate(snapshot["changes"]):
                vals = {
                    "project_id": project.id,
                    "sequence": (index + 1) * 10,
                    "change_type": item["type"],
                    "model": item["model"],
                    "view_id": item["view_id"] or False,
                    "view_type": item["view_type"],
                    "xpath": item["xpath"],
                    "position": item["position"],
                    "payload": json.dumps(item["payload"], sort_keys=True),
                }
                if item.get("model_line"):
                    line = project.new_model_ids.filtered(
                        lambda m, name=item["model_line"]: m.model == name
                    )
                    if line and not line.applied:
                        Change.create(dict(vals, view_id=False, model_line_id=line.id))
                        continue
                elif item.get("view_line"):
                    added = project.view_line_ids.filtered(
                        lambda v, i=item: v.model == i["model"]
                        and v.view_type == i["view_type"]
                    )
                    if added and not added.applied:
                        Change.create(dict(vals, view_id=False, view_line_id=added.id))
                        continue
                elif item["model"] in self.env and (
                    View.browse(item["view_id"] or 0).exists()
                ):
                    Change.create(vals)
                    continue
                skipped.append(
                    self.env._(
                        "a change of a view of %(model)s, gone",
                        model=item["model"],
                    )
                )
            project._touch()
        if not skipped:
            return True
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "warning",
                "sticky": True,
                "title": self.env._("Discarded"),
                "message": self.env._(
                    "Back to the last Apply, without what left the database "
                    "since: %(items)s.",
                    items="; ".join(skipped),
                ),
                "next": {"type": "ir.actions.client", "tag": "soft_reload"},
            },
        }

    def _studio_restore_company_rules(self, items):
        """Link each model line restored from ``items`` (the models of a
        snapshot) to the rule line of its option « Per company », named by
        its external id: the rules are restored after the models."""
        self.ensure_one()
        for item in items:
            if not item.get("company_rule"):
                continue
            line = self.new_model_ids.filtered(lambda m, i=item: m.model == i["model"])
            rule = self.rule_line_ids.filtered(
                lambda r, i=item: r.xml_name == i["company_rule"]
            )
            if line and rule:
                line._server_writing().write({"company_rule_id": rule[:1].id})

    def _studio_restore(self, Line, vals, item):
        """Create the line of ``vals`` (from ``item``, an entry of the
        snapshot) on ``Line``; when it no longer applies, create nothing.
        The existing groups of a rule or a group that left the database are
        left out of it, its ``group_refs`` / ``implied_refs`` keep them.
        Return the descriptions of what was left out."""
        self.ensure_one()
        label = item.get("name") or item.get("model") or ""
        gone = []
        menu = vals.get("menu_parent_id")
        if menu and not self.env["ir.ui.menu"].sudo().browse(menu).exists():
            gone.append(self.env._("its parent menu"))
        Groups = self.env["res.groups"].sudo()
        if vals.get("group_id") and not Groups.browse(vals["group_id"]).exists():
            gone.append(self.env._("a group"))
        for key in ("group_ids", "implied_group_ids"):
            if key in vals:
                ids = Groups.browse(vals[key][0][2]).exists().ids
                vals[key] = [(6, 0, ids)]
        model = vals.get("model")
        if (
            Line._name in ("erplibre.studio.access", "erplibre.studio.rule")
            and model not in self.env
            and model not in self._studio_new_models()
        ):
            gone.append(self.env._("its model"))
        if Line._name == "erplibre.studio.view":
            label = f"{model}.{vals.get('view_type')}"
            if model not in self.env:
                gone.append(self.env._("its model"))
        if not gone:
            try:
                with self.env.cr.savepoint():
                    Line.create(vals)
                return []
            except (UserError, ValidationError) as exc:
                gone.append(str(exc.args[0]))
            except psycopg2.Error as exc:
                gone.append(str(exc).strip())
        kind = {
            "erplibre.studio.app": self.env._("the app"),
            "erplibre.studio.group": self.env._("the group"),
            "erplibre.studio.model": self.env._("the model"),
            "erplibre.studio.access": self.env._("the access row on"),
            "erplibre.studio.rule": self.env._("the rule"),
            "erplibre.studio.view": self.env._("the view"),
        }[Line._name]
        return [
            self.env._(
                "%(kind)s %(name)s (%(why)s)",
                kind=kind,
                name=label,
                why=", ".join(gone),
            )
        ]

    # ── models, access rows and rules of the editor ─────────────────────

    def _studio_taken_models(self):
        """The model names a new model cannot take: those of the registry,
        transient and abstract ones included, and those of every model
        line."""
        return set(self.env.registry) | set(
            self.env["erplibre.studio.model"].sudo().search([]).mapped("model")
        )

    def _studio_check_free_model(self, model, line=None):
        """Raise ValidationError when ``model`` cannot be the technical name
        of the model line ``line`` (of a new line when None): the message
        of ``_studio_model_name_status``."""
        status = self._studio_model_name_status(model, line)
        if status["code"]:
            raise ValidationError(status["message"])

    # ── technical names of the new models ───────────────────────────────

    @api.model
    def _studio_model_name_rule(self):
        """The rule the technical names of new models follow on this
        database: {prefix_required, mode, label, text, detail}, the prefix
        and the mode of ``_studio_field_name_rule``, so that fields and
        models follow one rule; ``text`` and ``detail`` say why a model
        name without the prefix is refused or allowed."""
        rule = self._studio_field_name_rule()
        if rule["prefix_required"]:
            text = self.env._("Prefix x_ required on this database")
            detail = self.env._(
                "Models created outside the code carry x_ on a production database."
            )
        else:
            text = self.env._(
                "Without x_ allowed: development database (code_generator)"
            )
            detail = self.env._(
                "A model without x_ is written as is in the generated module; "
                "Odoo keeps it while ERPLibre studio generate is installed."
            )
        return {
            "prefix_required": rule["prefix_required"],
            "mode": rule["mode"],
            "label": rule["label"],
            "text": text,
            "detail": detail,
        }

    def _studio_reserved_model_names(self):
        """The model names a module on the addons path defines, which a new
        model cannot take: none here; ERPLibre studio generate reads them
        from the sources."""
        return set()

    def _studio_reserved_model_tables(self):
        """The tables of the models a module on the addons path defines,
        which the table of a new model (``studio_arch.model_table``) cannot
        be: none here; ERPLibre studio generate reads them from the
        sources."""
        return set()

    def _studio_model_name_owner(self, name, line=None):
        """Who already holds the model name ``name``, the model line
        ``line`` aside (the one renamed or checked; its applied model is
        its own): None, or {kind, name, project, table, model}. ``kind``:
        « model » when the registry or ir.model has it, « project » when
        another model line of any project creates it (``project`` names
        that project), « table » when its table (``studio_arch.model_table``)
        is the table of a model of the registry, of another model line, or
        a table of the database (``table``; ``model`` names the model that
        holds it, False for a table alone), « module » when a module on the
        addons path defines it (``_studio_reserved_model_names``) or a model
        of its table (``_studio_reserved_model_tables``; ``table`` names
        it)."""
        own = line.model if line and line.applied else None
        line_id = line.id if line else 0
        result = {"name": name, "project": False, "table": False, "model": False}
        if name != own and (
            name in self.env.registry or self.env["ir.model"].sudo()._get_id(name)
        ):
            return dict(result, kind="model", model=name)
        Line = self.env["erplibre.studio.model"].sudo()
        other = Line.search([("model", "=", name), ("id", "!=", line_id)], limit=1)
        if other:
            return dict(result, kind="project", project=other.project_id.name)
        table = studio_arch.model_table(name)
        if own is None or table != studio_arch.model_table(own):
            for model_name, Model in self.env.registry.items():
                if Model._table == table:
                    return dict(result, kind="table", table=table, model=model_name)
            for other in Line.search([("id", "!=", line_id)]):
                if studio_arch.model_table(other.model) == table:
                    return dict(
                        result,
                        kind="table",
                        table=table,
                        model=other.model,
                        project=other.project_id.name,
                    )
            if sql.table_exists(self.env.cr, table):
                return dict(result, kind="table", table=table)
        if name in self._studio_reserved_model_names():
            return dict(result, kind="module")
        if table in self._studio_reserved_model_tables():
            return dict(result, kind="module", table=table)
        return None

    def _studio_model_name_status(self, name, line=None):
        """{code, owner, message, detail, checks} of the technical name
        ``name`` of a new model, the model line ``line`` aside (see
        ``_studio_model_name_owner``). ``code``: None when the name
        applies, else the first of MODEL_NAME_CHECKS that fails; a model
        that takes no access row (``protected_model``) is reserved.
        ``checks``: [{key, ok, text}], the checks of MODEL_NAME_CHECKS each
        run on its own; the name is looked for only when its format is
        valid."""
        rule = self._studio_model_name_rule()
        passed = studio_arch.model_name_checks(name, rule["prefix_required"])
        passed["reserved"] = passed["reserved"] and not protected_model(name)
        owner = None
        if passed["format"]:
            owner = self._studio_model_name_owner(name, line)
        passed["unique"] = passed["format"] and owner is None
        texts = {
            "format": self.env._("Lower case letters, digits, _ and dots"),
            "reserved": self.env._("Not a reserved name"),
            "prefix": self.env._("Prefix that fits the rule of the database"),
            "unique": self.env._(
                "Unique among the models, the tables and the projects"
            ),
        }
        code = next((key for key in MODEL_NAME_CHECKS if not passed[key]), None)
        if code is None:
            message = self.env._("Available")
            detail = self.env._("No model, table nor project uses %(name)s.", name=name)
        elif code == "format":
            message = self.env._(
                "Invalid format: lower case letters, digits, _ and dots only"
            )
            detail = self.env._(
                "Each part starts with a letter; the table, the name with its "
                "dots as _, has %(size)s characters at most.",
                size=studio_arch.MODEL_NAME_SIZE,
            )
        elif code == "reserved":
            message = self.env._("Reserved model name (%(name)s)", name=name)
            detail = self.env._(
                "A Python keyword, a namespace of Odoo (ir, res, base, web, "
                "bus, report) or a model that takes no access right. The x_ "
                "prefix avoids this case."
            )
        elif code == "prefix":
            message, detail = rule["text"], rule["detail"]
        elif owner["kind"] == "project":
            message = self.env._(
                "The project %(project)s creates the model %(name)s already.",
                project=owner["project"],
                name=name,
            )
            detail = self.env._("Each new model needs its own name.")
        elif owner["kind"] == "table":
            message = self.env._(
                "Another model uses the table %(table)s", table=owner["table"]
            )
            detail = self.env._(
                "The table of a model is its name with its dots as _: two "
                "such names would share it."
            )
        elif owner["kind"] == "module" and owner["table"]:
            message = self.env._(
                "A module on the addons path uses the table %(table)s",
                table=owner["table"],
            )
            detail = self.env._(
                "Installed later, that module would share the table of this model."
            )
        elif owner["kind"] == "module":
            message = self.env._(
                "A module on the addons path defines %(name)s", name=name
            )
            detail = self.env._(
                "Installed later, that module would take the model over."
            )
        else:
            message = self.env._("The model %(name)s already exists.", name=name)
            detail = self.env._("Choose another name.")
        return {
            "code": code,
            "owner": owner,
            "message": message,
            "detail": detail,
            "checks": [
                {"key": key, "ok": passed[key], "text": texts[key]}
                for key in MODEL_NAME_CHECKS
            ],
        }

    def _studio_model_name_problems(self):
        """[{line_id, model, name, message}]: the model lines of the project
        not applied yet whose technical name does not apply, each checked
        with itself aside. An applied line keeps its name: its model
        exists."""
        self.ensure_one()
        result = []
        for line in self.new_model_ids:
            if line.applied:
                continue
            status = self._studio_model_name_status(line.model, line)
            if status["code"]:
                result.append(
                    {
                        "line_id": line.id,
                        "model": line.model,
                        "name": line.model,
                        "message": status["message"],
                    }
                )
        return result

    def _studio_foreign_models(self):
        """{model name: module} of the models the project created that a
        module other than its generated module defines now: the module of
        the class that defines the model in the registry
        (``_original_module``). A custom model has none."""
        self.ensure_one()
        result = {}
        for record in self.created_model_ids.exists():
            if record.state == "manual":
                continue
            Model = self.env.registry.get(record.model)
            module = getattr(Model, "_original_module", None) if Model else None
            if module and module != self.module_name:
                result[record.model] = module
        return result

    def _studio_foreign_model_refusal(self):
        """Why the project can no longer apply, revert nor generate its
        models, or False: another module defines one of them now
        (``_studio_foreign_models``), and owns its table and its fields."""
        foreign = self._studio_foreign_models()
        if not foreign:
            return False
        return self.env._(
            "Another module defines a model of this project now: %(models)s. "
            "The project can no longer apply, revert nor generate it.",
            models=", ".join(
                f"{model} ({module})" for model, module in sorted(foreign.items())
            ),
        )

    def _studio_menu_vals(self, menu, label=None):
        """The model line values of ``menu`` {mode, app_id | new_app: {name,
        icon}, parent_id, name, sequence}, as the editor sends it; the keys
        it lacks are left out. « new_app » creates the app; « app_name » /
        « app_icon » name a new app when the project has none yet."""
        vals = {}
        if "mode" in menu:
            vals["menu_mode"] = menu["mode"] or "app"
        if "parent_id" in menu:
            vals["menu_parent_id"] = int(menu["parent_id"] or 0) or False
        if "name" in menu:
            vals["menu_name"] = (menu["name"] or "").strip() or False
        if "sequence" in menu:
            vals["menu_sequence"] = int(menu["sequence"] or 0)
        if menu.get("app_id"):
            vals["app_id"] = self._studio_app_line(menu["app_id"]).id
        elif menu.get("new_app"):
            vals["app_id"] = self._studio_save_app(menu["new_app"], touch=False).id
        elif vals.get("menu_mode") == "app" and not self.app_ids and label:
            app = {
                "name": (menu.get("app_name") or "").strip() or label,
                "icon": menu.get("app_icon") or False,
            }
            vals["app_id"] = self._studio_save_app(app, touch=False).id
        return vals

    def _studio_create_model(self, values):
        """A new model line from ``values`` {name, model, chatter, menu: see
        ``_studio_menu_vals``, order, archivable, manual_order: see
        ``_studio_update_model``}, with the default access row (the internal
        users, every right). « app » without an app goes in the first app
        of the project, a new one named after the model when it has none.
        Return the line."""
        self.ensure_one()
        project = self._editing()
        label = (values.get("name") or "").strip()
        if not label:
            raise UserError(self.env._("A model needs a label."))
        model = (
            values.get("model") or ""
        ).strip() or studio_arch.model_name_from_label(
            label, self._studio_taken_models()
        )
        self._studio_check_free_model(model)
        menu = values.get("menu") or {}
        vals = {
            "project_id": self.id,
            "model": model,
            "name": label,
            "chatter": bool(values.get("chatter")),
            "menu_mode": "app",
            "sequence": max(self.new_model_ids.mapped("sequence") or [0]) + 10,
            **project._studio_menu_vals(dict({"mode": "app"}, **menu), label),
        }
        if vals["menu_mode"] == "app" and not vals.get("app_id"):
            vals["app_id"] = self.app_ids[:1].id
        line = project.env["erplibre.studio.model"].create(vals)
        options = {
            key: values[key]
            for key in ("order", *studio_arch.MODEL_OPTIONS)
            if key in values
        }
        if options:
            project._studio_write_options(line, options)
        project.env["erplibre.studio.access"].create(
            {
                "project_id": self.id,
                "model": model,
                "group_id": self.env.ref("base.group_user").id,
                **{perm: True for perm in PERMS},
            }
        )
        self._touch()
        return line

    def _studio_model_line(self, line_id):
        line = self.new_model_ids.filtered(lambda m: m.id == int(line_id or 0))
        if not line:
            raise UserError(self.env._("This model is not a model of the project."))
        return line

    def _studio_update_model(self, line, values):
        """Write ``values`` {name, model, chatter, menu, sequence, order,
        archivable, manual_order} on the model line ``line`` (see
        ``erplibre.studio.model.write`` and ``_studio_write_options``)."""
        self.ensure_one()
        project = self._editing()
        line = line.with_context(**{NO_TOUCH_KEY: True})
        vals = project._studio_menu_vals(values.get("menu") or {}, line.name)
        if vals.get("menu_mode") == "app" and not (vals.get("app_id") or line.app_id):
            vals["app_id"] = self.app_ids[:1].id
        if "name" in values:
            vals["name"] = (values["name"] or "").strip()
        if "chatter" in values:
            vals["chatter"] = bool(values["chatter"])
        if "sequence" in values:
            vals["sequence"] = int(values["sequence"] or 0)
        if (values.get("model") or "").strip():
            vals["model"] = values["model"].strip()
            if vals["model"] != line.model:
                self._studio_check_free_model(vals["model"], line)
        line.write(vals)
        options = {
            key: values[key]
            for key in ("order", *studio_arch.MODEL_OPTIONS)
            if key in values
        }
        if options:
            project._studio_write_options(line, options)
        self._touch()
        return line

    def _studio_write_options(self, line, values):
        """Write the options of ``values`` {order, archivable, manual_order,
        per_company} on the model line ``line``. An option turned on needs
        its field free on the applied model, or the option's own
        (``_studio_option_own_field``): an option turned off after Apply and
        on again before the next one removes nothing. « Manual order »
        turned on sorts by ``x_sequence`` a model without order; turned off,
        it clears an order that names ``x_sequence``. « Per company »
        turned on adds its rule line (``_studio_company_rule``), under the
        external id of the applied rule when the option had one; turned
        off, it removes that line when the project still has it. The order
        is checked last, against the fields the options give
        (``_studio_clean_order``)."""
        line = line.with_context(**{NO_TOUCH_KEY: True})
        vals = {}
        for key, (name, _ttype, _label) in studio_arch.MODEL_OPTIONS.items():
            if key not in values or bool(values[key]) == line[key]:
                continue
            vals[key] = bool(values[key])
            if (
                vals[key]
                and line.applied
                and name in self.env[line.model]._fields
                and not self._studio_option_own_field(line, key)
            ):
                raise UserError(
                    self.env._(
                        "%(model)s already has a field %(field)s.",
                        model=line.model,
                        field=name,
                    )
                )
        manual = studio_arch.MODEL_OPTIONS["manual_order"][0]
        order = values.get("order", line.order) or ""
        if vals.get("manual_order") and not order.strip():
            order = studio_arch.MANUAL_ORDER
        elif vals.get("manual_order") is False:
            try:
                if manual in studio_arch.order_fields(order):
                    order = ""
            except studio_arch.ArchError:
                pass
        company_rule = line.company_rule_id
        line.write(vals)
        if vals.get("per_company"):
            item = self._studio_applied_model_item(line.model)
            self._studio_company_rule(line, item.get("company_rule"))
        elif vals.get("per_company") is False:
            company_rule.unlink()
        if "order" in values or order != (line.order or ""):
            line.write({"order": self._studio_clean_order(line, order) or False})

    def _studio_company_rule(self, line, xml_name=None):
        """Create the rule line of the option « Per company » of the model
        line ``line`` and keep it on the line: global, every operation,
        the records of the companies of the user and those of no company
        (``COMPANY_RULE_DOMAIN``). ``xml_name``: the external id name the
        line takes when no rule line of the project has it (the one of the
        applied rule, which Apply then updates instead of replacing it).
        The line is an ordinary rule of the project from then on: the
        Security space edits or removes it."""
        label = (line.name or "").strip() or line.model
        rule = self._studio_save_rule(
            {
                "name": self.env._("%(model)s: multi-company", model=label),
                "model": line.model,
                "domain": studio_arch.COMPANY_RULE_DOMAIN,
                "global_rule": True,
                **{perm: True for perm in PERMS},
            }
        )
        if xml_name and xml_name not in (self.rule_line_ids - rule).mapped("xml_name"):
            rule._server_writing().write({"xml_name": xml_name})
        line._server_writing().write({"company_rule_id": rule.id})
        return rule

    def _studio_clean_order(self, line, text):
        """The order ``text`` of the model line ``line``, normalised:
        « name asc » or « name desc » terms joined by « , »; empty for
        none. UserError when it is no order, or names a field the records
        cannot be sorted by (``_studio_sortable_fields``)."""
        text = (text or "").strip()
        if not text:
            return ""
        try:
            terms = studio_arch.order_terms(text)
        except studio_arch.ArchError as exc:
            raise UserError(self._arch_message(exc)) from exc
        sortable = self._studio_sortable_fields(line)
        for name, _direction in terms:
            if name not in sortable:
                raise UserError(
                    self.env._("The records cannot be sorted by %(name)s.", name=name)
                )
        return ", ".join(f"{name} {direction}" for name, direction in terms)

    def _studio_remove_model(self, line):
        """Remove the model line ``line`` and what names its model (see
        ``erplibre.studio.model.unlink``); Apply then removes it from the
        database."""
        self.ensure_one()
        line.with_context(**{NO_TOUCH_KEY: True}).unlink()
        self._touch()

    def _studio_app_line(self, app_id):
        app = self.app_ids.filtered(lambda a: a.id == int(app_id or 0))
        if not app:
            raise UserError(self.env._("This app is not an app of the project."))
        return app

    def _studio_save_app(self, values, touch=True):
        """Create the app of ``values`` {id, name, icon, menu_sequence,
        sequence}, or write the one of ``id``. Return it."""
        self.ensure_one()
        project = self._editing()
        vals = {}
        if "name" in values:
            vals["name"] = (values["name"] or "").strip()
        if "icon" in values:
            vals["icon"] = values["icon"] or False
        for key in ("menu_sequence", "sequence"):
            if key in values:
                vals[key] = int(values[key] or 0)
        if values.get("id"):
            app = project._studio_app_line(values["id"])
            app.with_context(**{NO_TOUCH_KEY: True}).write(vals)
        else:
            if not vals.get("name"):
                raise UserError(self.env._("An app needs a name."))
            vals.setdefault(
                "sequence", max(self.app_ids.mapped("sequence") or [0]) + 10
            )
            app = project.env["erplibre.studio.app"].create(
                dict(vals, project_id=self.id)
            )
        if touch:
            self._touch()
        return app

    def _studio_update_app(self, values):
        """Write the first app of the project from ``values`` {name, icon,
        sequence}; a project without app gets one. The editor of a single
        app calls it."""
        self.ensure_one()
        vals = {k: values[k] for k in ("name", "icon") if k in values}
        if "sequence" in values:
            vals["menu_sequence"] = values["sequence"]
        if self.app_ids:
            vals["id"] = self.app_ids[:1].id
        return self._studio_save_app(vals)

    def _studio_remove_app(self, app):
        """Remove the app ``app``: refused while a model or a group of the
        project goes in it (``erplibre.studio.app.unlink``)."""
        self.ensure_one()
        app.with_context(**{NO_TOUCH_KEY: True}).unlink()
        self._touch()

    def _studio_group_line(self, group_id):
        group = self.group_line_ids.filtered(lambda g: g.id == int(group_id or 0))
        if not group:
            raise UserError(self.env._("This group is not a group of the project."))
        return group

    def _studio_save_group(self, values):
        """Create the group of ``values`` {id, name, app_id, comment,
        implied_line_ids, implied_group_ids}, or write the one of ``id``. A
        new group implies the internal users unless ``implied_group_ids``
        says otherwise. Return it."""
        self.ensure_one()
        project = self._editing()
        vals = {}
        if "name" in values:
            vals["name"] = (values["name"] or "").strip()
        if "comment" in values:
            vals["comment"] = (values["comment"] or "").strip() or False
        if "app_id" in values:
            vals["app_id"] = self._studio_app_line(values["app_id"]).id
        if "implied_line_ids" in values:
            lines = [
                self._studio_group_line(i).id for i in values["implied_line_ids"] or []
            ]
            vals["implied_line_ids"] = [(6, 0, lines)]
        if "implied_group_ids" in values:
            ids = [int(i) for i in values["implied_group_ids"] or []]
            vals["implied_group_ids"] = [(6, 0, ids)]
        if values.get("id"):
            group = project._studio_group_line(values["id"])
            group.with_context(**{NO_TOUCH_KEY: True}).write(vals)
        else:
            if not vals.get("name"):
                raise UserError(self.env._("A group needs a name."))
            if not vals.get("app_id"):
                raise UserError(
                    self.env._("A group goes in an app of the project: choose it.")
                )
            vals.setdefault(
                "implied_group_ids", [(6, 0, [self.env.ref("base.group_user").id])]
            )
            vals["sequence"] = max(self.group_line_ids.mapped("sequence") or [0]) + 10
            group = project.env["erplibre.studio.group"].create(
                dict(vals, project_id=self.id)
            )
        self._touch()
        return group

    def _studio_remove_group(self, group):
        """Remove the group ``group`` with its access rows; the rules and the
        groups of the project that named it lose it."""
        self.ensure_one()
        project = self._editing()
        project._studio_check_group_in_views(group)
        project.access_line_ids.filtered(lambda a: a.group_line_id == group).unlink()
        group.with_context(**{NO_TOUCH_KEY: True}).unlink()
        self._touch()

    def _studio_check_group_in_views(self, group):
        """Raise UserError while a change of the project shows a node of a
        view for the group of the project ``group`` only (« groups »): the
        view would name an external id that no longer exists."""
        self.ensure_one()
        xmlid = group._studio_full_xmlid()
        items = [
            f"{change._studio_view_label()} · {change.xpath}"
            for change in self.change_ids
            if change.change_type == "set_attribute"
            and xmlid in (change._payload().get("groups") or [])
        ]
        if items:
            raise UserError(
                self.env._(
                    "The group %(group)s cannot be removed: %(items)s show for "
                    "it. Remove it from these fields first.",
                    group=group.name,
                    items=", ".join(sorted(set(items))),
                )
            )

    def _studio_set_access(self, rows):
        """Replace the access rows of the project by ``rows`` [{model,
        group_id | group_line_id, perm_read, perm_write, perm_create,
        perm_unlink}]; a row that gives no right is left out."""
        self.ensure_one()
        project = self._editing()
        Access = project.env["erplibre.studio.access"]
        existing = {
            (a.model, a.group_id.id, a.group_line_id.id): a
            for a in self.access_line_ids
        }
        seen = set()
        for row in rows or []:
            perms = {perm: bool(row.get(perm)) for perm in PERMS}
            line_id = int(row.get("group_line_id") or 0)
            group_id = 0 if line_id else int(row.get("group_id") or 0)
            if line_id:
                line_id = self._studio_group_line(line_id).id
            key = ((row.get("model") or "").strip(), group_id, line_id)
            if not any(perms.values()) or key in seen or not (group_id or line_id):
                continue
            seen.add(key)
            line = existing.get(key)
            if not line:
                Access.create(
                    {
                        "project_id": self.id,
                        "model": key[0],
                        "group_id": group_id or False,
                        "group_line_id": line_id or False,
                        **perms,
                    }
                )
            elif any(line[perm] != value for perm, value in perms.items()):
                line.with_context(**{NO_TOUCH_KEY: True}).write(perms)
        Access.browse(
            [line.id for key, line in existing.items() if key not in seen]
        ).unlink()
        self._touch()

    def _studio_rule_line(self, rule_id):
        rule = self.rule_line_ids.filtered(lambda r: r.id == int(rule_id or 0))
        if not rule:
            raise UserError(self.env._("This rule is not a rule of the project."))
        return rule

    def _studio_save_rule(self, values):
        """Create the rule line of ``values`` {id, name, model, domain,
        group_ids, group_line_ids, global_rule, perm_*}, or write the one of
        ``id``. Saving the groups records them again: a group that left the
        database is no longer flagged. Return it."""
        self.ensure_one()
        project = self._editing()
        if not (values.get("name") or "").strip():
            raise UserError(self.env._("A rule needs a name."))
        vals = {
            "name": (values.get("name") or "").strip(),
            "model": (values.get("model") or "").strip(),
            "domain_force": (values.get("domain") or "").strip() or "[]",
            "group_ids": [(6, 0, [int(g) for g in values.get("group_ids") or []])],
            **{perm: bool(values.get(perm)) for perm in PERMS},
        }
        if "group_line_ids" in values:
            lines = [
                project._studio_group_line(i).id for i in values["group_line_ids"] or []
            ]
            vals["group_line_ids"] = [(6, 0, lines)]
        if "global_rule" in values:
            vals["global_rule"] = bool(values["global_rule"])
        if values.get("id"):
            rule = project._studio_rule_line(values["id"]).with_context(
                **{NO_TOUCH_KEY: True}
            )
            rule.write(vals)
        else:
            vals["project_id"] = self.id
            vals["sequence"] = max(self.rule_line_ids.mapped("sequence") or [0]) + 10
            rule = project.env["erplibre.studio.rule"].create(vals)
        self._touch()
        return rule

    def _studio_remove_rule(self, rule):
        self.ensure_one()
        rule.with_context(**{NO_TOUCH_KEY: True}).unlink()
        self._touch()

    def _studio_default_arch(self, line, view_type):
        """The arch of the default ``view_type`` view of the model line
        ``line``: the one Apply writes and a generated module defines."""
        return studio_arch.default_model_arch(
            view_type,
            (line.name or "").strip(),
            line.chatter,
            archivable=line.archivable,
            manual_order=line.manual_order,
            per_company=line.per_company,
        )

    # ── views the project adds ──────────────────────────────────────────

    def _studio_view_line(self, model, view_type):
        """The view line of the project that adds the ``view_type`` view of
        ``model``, or an empty recordset."""
        lines = self.view_line_ids if len(self) == 1 else self.view_line_ids.browse()
        return lines.filtered(
            lambda line: line.model == model and line.view_type == view_type
        )[:1]

    def _studio_added_view(self, model, view_type):
        """The view the project adds as ``view_type`` view of ``model``,
        while Apply has not created it (``StudioAddedView``), else None."""
        line = self._studio_view_line(model, view_type)
        if line and not line.applied:
            return added_view(line)
        return None

    def _studio_view_line_of(self, view):
        """The view line behind ``view``: the line of a ``StudioAddedView``,
        or the line whose Apply created the view; else an empty
        recordset."""
        if is_added_view(view):
            return view.line
        if not view or is_pending_view(view):
            return self.view_line_ids.browse()
        return self.view_line_ids.filtered(lambda line: line.view_id == view)[:1]

    @api.model
    def _studio_view_fields(self, model):
        """(name field, date field, group field) of the default arch of a
        view added to ``model``: the field a record shows by, the first of
        ``create_date`` or a stored date, and the first of ``create_uid`` or
        a stored many2one; None where the model has none."""
        Model = self.env[model]
        name = Model._rec_name_fallback()
        stored = [
            (fname, field)
            for fname, field in Model._fields.items()
            if field.store and fname != "id"
        ]
        date = next(
            (
                fname
                for fname in ["create_date"]
                + [n for n, f in stored if f.type in studio_arch.DATE_TYPES]
                if fname in Model._fields
                and Model._fields[fname].type in studio_arch.DATE_TYPES
            ),
            None,
        )
        group = next(
            (
                fname
                for fname in ["create_uid"]
                + [n for n, f in stored if f.type == "many2one"]
                if fname in Model._fields and Model._fields[fname].type == "many2one"
            ),
            None,
        )
        return name, date, group

    @api.model
    def _studio_calendar_date(self, model):
        """(field, readonly): the date field a calendar added to ``model``
        starts its events on. The first stored date or datetime field a user
        writes, the calendar field of the model (``_date_name``),
        « date_start » and « date » first; else ``create_date``, readonly,
        which no event can move to; (None, False) without either."""
        Model = self.env[model]
        fields = Model._fields
        preferred = [getattr(Model, "_date_name", "date"), "date_start", "date"]
        names = preferred + [n for n in fields if n not in preferred]
        for fname in names:
            field = fields.get(fname)
            if (
                field
                and field.type in studio_arch.DATE_TYPES
                and field.store
                and not field.readonly
                and fname not in ("create_date", "write_date")
            ):
                return fname, False
        field = fields.get("create_date")
        if field and field.type in studio_arch.DATE_TYPES:
            return "create_date", True
        return None, False

    @api.model
    def _studio_parent_field(self, model):
        """The many2one of ``model`` to itself a hierarchy added to it
        reads: the parent field of the model (``_parent_name``), else
        parent_id, else its first such field; None without one. The field
        is stored: the hierarchy searches by it."""
        Model = self.env[model]
        fields = Model._fields

        def fits(fname):
            field = fields.get(fname)
            return bool(
                field
                and field.type == "many2one"
                and field.comodel_name == model
                and field.store
            )

        preferred = [Model._parent_name, "parent_id"]
        names = preferred + [n for n in fields if n not in preferred]
        return next((fname for fname in names if fits(fname)), None)

    @api.model
    def _studio_leaflet_fields(self, model):
        """{attribute: field} of the map added to ``model``: the first
        stored float whose name ends with « latitude », and with
        « longitude », the record name as popup title when a popup shows
        it (LEAFLET_TEXT_TYPES); no address, which the user chooses. An
        attribute without a field is left out: its lane creates one."""
        Model = self.env[model]
        fields = Model._fields
        result = {}
        for attribute, suffix in (
            ("field_latitude", "latitude"),
            ("field_longitude", "longitude"),
        ):
            name = next(
                (
                    fname
                    for fname, field in fields.items()
                    if field.type == "float" and field.store and fname.endswith(suffix)
                ),
                None,
            )
            if name:
                result[attribute] = name
        title = Model._rec_name_fallback()
        if title in fields and fields[title].type in studio_arch.LEAFLET_TEXT_TYPES:
            result["field_title"] = title
        return result

    @api.model
    def _studio_has_activities(self, model):
        """Whether ``model``, a model of the registry, inherits
        mail.activity.mixin: an activity view reads its activities. False
        without mail."""
        return (
            "mail.activity.mixin" in self.env
            and model in self.env
            and isinstance(self.env[model], self.env.registry["mail.activity.mixin"])
        )

    def _studio_add_view(self, model, view_type):
        """Add to the draft the ``view_type`` view of the existing ``model``,
        which has none of that type: a view line with its default arch
        (``arch.default_view_arch``). A map of a model without
        LEAFLET_DATE_FIELD comes with one add_field change on its line that
        creates it (``_studio_leaflet_date_definition``). A GeoEngine view
        needs a geo field of the model in the database, and comes with its
        default layers (``_studio_default_geo_layers``). Return the line;
        UserError when the view cannot be added."""
        self.ensure_one()
        self = self._editing()
        Editor = self.env["erplibre.studio.editor"]
        label = Editor._view_type_labels().get(view_type, view_type)
        if view_type not in self._view_types():
            if view_type in studio_arch.OPTIONAL_VIEW_MODULES:
                raise UserError(
                    Editor._view_reason("needs_module", label, model, view_type)
                )
            raise UserError(
                self.env._("The studio does not edit %(type)s views.", type=label)
            )
        if model not in self.env:
            if self._studio_pending_line(model):
                raise UserError(
                    Editor._view_reason("apply_first", label, model, view_type)
                )
            raise UserError(self.env._("Unknown model %(model)s.", model=model))
        Model = self.env[model]
        if Model._abstract or Model._transient:
            raise UserError(
                self.env._(
                    "%(model)s stores no records: the studio adds no view to it.",
                    model=model,
                )
            )
        View = self.env["ir.ui.view"].sudo()
        if View.default_view(model, view_type):
            raise UserError(
                self.env._(
                    "%(model)s already has a %(type)s view.", model=model, type=label
                )
            )
        other = (
            self.env["erplibre.studio.view"]
            .sudo()
            .search([("model", "=", model), ("view_type", "=", view_type)], limit=1)
        )
        if other:
            raise UserError(
                self.env._(
                    "The project %(project)s already adds a %(type)s view to "
                    "%(model)s.",
                    project=other.project_id.name,
                    type=label,
                    model=model,
                )
            )
        name, date, group = self._studio_view_fields(model)
        if view_type == "timeline" and not (date and group):
            raise UserError(
                self.env._(
                    "A timeline needs a date field and a many2one on %(model)s.",
                    model=model,
                )
            )
        readonly_date = False
        if view_type == "calendar":
            date, readonly_date = self._studio_calendar_date(model)
            if not date:
                raise UserError(
                    self.env._(
                        "A calendar needs a stored date field on %(model)s.",
                        model=model,
                    )
                )
        need = Editor._view_need(view_type, model)
        if need:
            raise UserError(Editor._view_reason(need, label, model, view_type))
        leaflet = date_definition = None
        if view_type == "leaflet_map":
            date_definition = self._studio_leaflet_date_definition(model, label)
            leaflet = self._studio_leaflet_fields(model)
        # The view loads the geo field of its vector layer: the first one.
        geo_fields = (
            self._studio_geo_fields(model)[:1] if view_type == "geoengine" else ()
        )
        parent = None
        if view_type == "hierarchy":
            parent = self._studio_parent_field(model)
            if not parent:
                raise UserError(
                    self.env._(
                        "A hierarchy needs a many2one from %(model)s to itself.",
                        model=model,
                    )
                )
        # The source label of the model: the arch goes as is into a module.
        description = Model._description or model
        arch = studio_arch.default_view_arch(
            view_type,
            description,
            name,
            date,
            group,
            readonly_date=readonly_date,
            parent_field=parent,
            leaflet=leaflet,
            geo_fields=geo_fields,
        )
        sequence = max(self.view_line_ids.mapped("sequence") or [0]) + 10
        line = (
            self.env["erplibre.studio.view"]
            ._server_writing()
            .with_context(**{NO_TOUCH_KEY: True})
            .create(
                {
                    "project_id": self.id,
                    "model": model,
                    "view_type": view_type,
                    "arch": arch,
                    "sequence": sequence,
                }
            )
        )
        if date_definition:
            self._add_change(
                added_view(line),
                "add_field",
                f"/{view_type}",
                "inside",
                {
                    "field_name": studio_arch.LEAFLET_DATE_FIELD,
                    "field": date_definition,
                    "node_attrs": {},
                    # The renderer reads the field by this name.
                    "name_auto": False,
                },
            )
        self._studio_default_geo_layers(line, geo_fields)
        self._touch()
        return line

    @api.model
    def _studio_geo_fields(self, model):
        """The stored geo fields (GEO_TYPES) ``model`` has in the registry,
        in the order of its fields: a GeoEngine view draws a field Apply
        created."""
        if model not in self.env:
            return ()
        return tuple(
            name
            for name, field in self.env[model]._fields.items()
            if field.type in studio_arch.GEO_TYPES and field.store
        )

    def _studio_default_geo_layers(self, line, geo_fields):
        """The layers of the new GeoEngine view ``line``: an OpenStreetMap
        background, and the first field of ``geo_fields`` drawn as it is,
        shown when the map opens. None without a geo field."""
        if not geo_fields:
            return
        geo_field = geo_fields[0]
        field = self.env[line.model]._fields[geo_field]
        # The source labels: they go as they are into a generated module.
        self.env["erplibre.studio.geo.layer"].with_context(
            **{NO_TOUCH_KEY: True}
        ).create(
            [
                {
                    "project_id": self.id,
                    "view_line_id": line.id,
                    "kind": "raster",
                    "sequence": 10,
                    "name": "OpenStreetMap",
                    "raster_type": "osm",
                },
                {
                    "project_id": self.id,
                    "view_line_id": line.id,
                    "kind": "vector",
                    "sequence": 10,
                    "name": field.string or geo_field,
                    "geo_field": geo_field,
                    "geo_repr": "basic",
                    "active_on_startup": True,
                },
            ]
        )

    @api.model
    def _studio_geo_attribute_fields(self, model):
        """{name: type} of the stored fields of ``model`` in the registry
        whose values color a colored range (GEO_ATTRIBUTE_TYPES)."""
        if model not in self.env:
            return {}
        return {
            name: field.type
            for name, field in self.env[model]._fields.items()
            if field.type in studio_arch.GEO_ATTRIBUTE_TYPES and field.store
        }

    def _studio_geo_line(self, view):
        """The view line of the project behind the GeoEngine view ``view``
        (``_studio_view_line_of``); UserError for another view."""
        line = self._studio_view_line_of(view)
        if not line or line.view_type != "geoengine":
            raise UserError(
                self.env._("Layers belong to a GeoEngine view the project adds.")
            )
        return line

    def _studio_geo_layer(self, line, layer_id):
        """The layer ``layer_id`` of the view line ``line``; UserError when
        it is not one of its layers."""
        layer = line.layer_ids.filtered(lambda item: item.id == int(layer_id or 0))
        if not layer:
            raise UserError(self.env._("This layer is not a layer of the view."))
        return layer

    @api.model
    def _studio_geo_color(self, value):
        """The color ``value`` as « #rrggbb » in lower case, False when
        empty; UserError for another text."""
        text = (value or "").strip()
        if not text:
            return False
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", text):
            raise UserError(
                self.env._("A color reads #rrggbb: %(color)s does not.", color=text)
            )
        return text.lower()

    def _studio_geo_layer_values(self, line, values):
        """The values of a vector layer of the GeoEngine view line ``line``
        from ``values`` {name, geo_field, geo_repr, attribute_field,
        classification, nb_class, begin_color, end_color,
        active_on_startup}, cleaned as geoengine.vector.layer accepts them
        at Apply (its _check_geo_repr): a colored range reads an attribute
        of GEO_ATTRIBUTE_TYPES, a number (GEO_NUMBER_TYPES) for an interval
        or a quantile, in 1 to 20 classes. A basic layer keeps its color only.
        UserError for a value it refuses."""
        model = line.model
        layer_fields = self.env["erplibre.studio.geo.layer"]._fields
        name = (values.get("name") or "").strip()
        if not name:
            raise UserError(self.env._("A layer needs a name."))
        geo_field = values.get("geo_field") or ""
        if geo_field not in self._studio_geo_fields(model):
            raise UserError(
                self.env._(
                    "A layer draws a geo field of %(model)s that Apply created: "
                    "%(field)s is not one.",
                    model=model,
                    field=geo_field or "-",
                )
            )
        geo_repr = values.get("geo_repr") or "basic"
        if geo_repr not in dict(layer_fields["geo_repr"].selection):
            raise UserError(
                self.env._("Unknown representation %(repr)s.", repr=geo_repr)
            )
        vals = {
            "name": name,
            "geo_field": geo_field,
            "geo_repr": geo_repr,
            "attribute_field": False,
            "classification": False,
            "nb_class": 1,
            "begin_color": self._studio_geo_color(values.get("begin_color")),
            "end_color": False,
            "active_on_startup": bool(values.get("active_on_startup")),
        }
        if geo_repr != "colored":
            return vals
        attributes = self._studio_geo_attribute_fields(model)
        attribute = values.get("attribute_field") or ""
        if attribute not in attributes:
            raise UserError(
                self.env._(
                    "A colored range needs the field whose values color it: a "
                    "number, a date, a text or a selection of %(model)s.",
                    model=model,
                )
            )
        classification = values.get("classification") or "unique"
        if classification not in dict(layer_fields["classification"].selection):
            raise UserError(
                self.env._(
                    "Unknown classification %(classification)s.",
                    classification=classification,
                )
            )
        numbers = studio_arch.GEO_NUMBER_TYPES
        if classification != "unique" and attributes[attribute] not in numbers:
            raise UserError(
                self.env._(
                    "An interval or a quantile classification needs a number "
                    "field: %(field)s is not one.",
                    field=attribute,
                )
            )
        try:
            nb_class = int(values.get("nb_class") or 0)
        except (TypeError, ValueError):
            nb_class = 0
        low, high = studio_arch.GEO_CLASS_RANGE
        if not low <= nb_class <= high:
            raise UserError(
                self.env._(
                    "A colored range has %(low)s to %(high)s classes.",
                    low=low,
                    high=high,
                )
            )
        vals.update(
            {
                "attribute_field": attribute,
                "classification": classification,
                "nb_class": nb_class,
                "end_color": self._studio_geo_color(values.get("end_color")),
            }
        )
        return vals

    def _studio_save_geo_layer(self, line, values):
        """Create the vector layer of ``values`` (see
        ``_studio_geo_layer_values``) on the GeoEngine view line ``line``,
        after its other vector layers, or write the one of ``id``; a
        ``sequence`` moves it (``_studio_move_geo_layer``). The background
        is not edited. The view loads the geo field and the attribute the
        layer reads, the renderer finds them in the records: a field it
        does not load yet gets an add_existing_field change, its own step
        of Undo. Return the layer."""
        self.ensure_one()
        project = self._editing()
        vals = project._studio_geo_layer_values(line, values)
        if values.get("id"):
            layer = project._studio_geo_layer(line, values["id"])
            if layer.kind != "vector":
                raise UserError(
                    self.env._(
                        "The background of the map is not edited: only the "
                        "layers of geo fields are."
                    )
                )
            layer.with_context(**{NO_TOUCH_KEY: True}).write(vals)
            if values.get("sequence"):
                project._studio_move_geo_layer(layer, int(values["sequence"]))
        else:
            vectors = line.layer_ids.filtered(lambda item: item.kind == "vector")
            layer = project.env["erplibre.studio.geo.layer"].create(
                dict(
                    vals,
                    project_id=self.id,
                    view_line_id=line.id,
                    kind="vector",
                    sequence=max(vectors.mapped("sequence") or [0]) + 10,
                )
            )
        project._studio_load_geo_fields(
            line, [vals["geo_field"], vals["attribute_field"]]
        )
        self._touch()
        return layer

    def _studio_move_geo_layer(self, layer, sequence):
        """Give the layer ``layer`` the place ``sequence``; the layer of the
        same kind of its view that had it takes the former place of
        ``layer``. Each write is flushed on its own, through a free place:
        the layers of a view keep a unique (kind, sequence) at each
        step."""
        old = layer.sequence
        if sequence == old:
            return
        if sequence < 1:
            raise UserError(self.env._("A layer takes a place from 1."))
        same = layer.view_line_id.layer_ids.filtered(
            lambda item: item.kind == layer.kind
        )
        other = same.filtered(lambda item: item.sequence == sequence)
        layer = layer.with_context(**{NO_TOUCH_KEY: True})
        if other:
            other = other.with_context(**{NO_TOUCH_KEY: True})
            other.write({"sequence": max(same.mapped("sequence")) + 1})
            other.flush_recordset(["sequence"])
        layer.write({"sequence": sequence})
        layer.flush_recordset(["sequence"])
        if other:
            other.write({"sequence": old})
            other.flush_recordset(["sequence"])

    def _studio_load_geo_fields(self, line, names):
        """Load in the GeoEngine view of ``line`` the fields of ``names``
        it does not load yet, before its templates: one add_existing_field
        change each."""
        view = self._studio_added_view(line.model, line.view_type) or line.view_id
        if not view:
            return
        arch, _errors = self._draft_arch(view)
        loaded = self._loaded_fields(arch)
        templates = arch.find("templates")
        for name in dict.fromkeys(names):
            if not name or name in loaded:
                continue
            op = {"type": "add_existing_field", "field_name": name}
            if templates is None:
                op.update(target=f"/{arch.tag}", position="inside")
            else:
                op.update(target=f"/{arch.tag}/templates", position="before")
            self._apply_operation(view, op)
            loaded.add(name)

    def _studio_remove_geo_layer(self, layer):
        """Take ``layer`` out of its view; the next Apply removes the layer
        it wrote. The last background stays, and so does the last vector
        layer: the map draws at least one geo field."""
        self.ensure_one()
        same = layer.view_line_id.layer_ids.filtered(
            lambda item: item.kind == layer.kind
        )
        if len(same) == 1:
            if layer.kind == "raster":
                raise UserError(
                    self.env._("The map keeps its background: it is not removed.")
                )
            raise UserError(
                self.env._(
                    "The map draws at least one geo field: its last layer is "
                    "not removed."
                )
            )
        layer.with_context(**{NO_TOUCH_KEY: True}).unlink()
        self._touch()

    def _studio_leaflet_date_definition(self, model, label):
        """The definition of the date field LEAFLET_DATE_FIELD a map added to
        ``model`` creates with its view line: a date with the label of
        base_geolocalize; None when ``model`` has the field. UserError
        « needs_field » on a database where a new field needs the x_
        prefix, and when the name does not apply
        (``_studio_field_name_problem``)."""
        name = studio_arch.LEAFLET_DATE_FIELD
        if name in self.env[model]._fields:
            return None
        if self._studio_field_name_rule()["prefix_required"]:
            raise UserError(
                self.env["erplibre.studio.editor"]._view_reason(
                    "needs_field", label, model, "leaflet_map"
                )
            )
        problem = self._studio_field_name_problem(model, name)
        if problem:
            raise UserError(problem["message"])
        # The source label: it goes as is into a generated module.
        _name, definition = self._clean_field_definition(
            model,
            {"ttype": "date", "field_description": "Geolocation Date"},
            name=name,
        )
        return definition

    def _studio_added_line(self, line_id):
        line = self.view_line_ids.filtered(lambda v: v.id == int(line_id or 0))
        if not line:
            raise UserError(self.env._("This view is not in the project."))
        return line

    def _studio_remove_view(self, line):
        """Take the view ``line`` adds out of the draft, with its changes;
        once applied, the next Apply removes the view from the database."""
        self.ensure_one()
        line.with_context(**{NO_TOUCH_KEY: True}).unlink()
        self._touch()

    # ── apply / revert ──────────────────────────────────────────────────

    def _studio_xmlname(self, view):
        xml_id = view.xml_id
        base = xml_id.replace(".", "_") if xml_id else f"view_{view.id}"
        return f"{base}_studio"

    def _studio_view(self, view):
        """The inherited view of the project on ``view``, by its external id
        under the module name."""
        data = (
            self.env["ir.model.data"]
            .sudo()
            .search(
                [
                    ("module", "=", self.module_name),
                    ("name", "=", self._studio_xmlname(view)),
                    ("model", "=", "ir.ui.view"),
                ],
                limit=1,
            )
        )
        return self.env["ir.ui.view"].sudo().browse(data.res_id).exists()

    def _rename_studio_xmlids(self, new_name):
        """Move the external ids of what the project created to the module
        ``new_name``. An inherited view on a default view of a new model
        is named after the external id of that view, which starts with the
        module (``_studio_xmlname``): its external id and its name follow,
        so that the next Apply finds it. The « groups » attributes that name
        a group of the project follow too (``_studio_rename_group_refs``)."""
        self.ensure_one()
        old_name = self.module_name
        self._studio_rename_group_refs(
            {
                f"{old_name}.{group.xml_name}": f"{new_name}.{group.xml_name}"
                for group in self.group_line_ids
                if group.xml_name
            }
        )
        Data = self.env["ir.model.data"].sudo()
        records = (
            [self.studio_view_ids, self.field_ids]
            + [self[name] for name in CREATED_FIELDS.values()]
            + list(self._studio_geo_layer_records().values())
        )
        for record in records:
            if record:
                Data.search(
                    [
                        ("module", "=", old_name),
                        ("model", "=", record._name),
                        ("res_id", "in", record.ids),
                    ]
                ).write({"module": new_name})
        if self.created_group_ids:
            # ir.model.data clears the « groups » cache only on a write of
            # its « model »: without this, the check of a view and
            # has_group still know a group under its former external id.
            self.env.registry.clear_cache("groups")
        prefix = f"{old_name}_"
        for view in self.studio_view_ids.sudo():
            if view.inherit_id not in self.created_view_ids:
                continue
            data = Data.search(
                [
                    ("module", "=", new_name),
                    ("model", "=", "ir.ui.view"),
                    ("res_id", "=", view.id),
                ],
                limit=1,
            )
            if data.name.startswith(prefix):
                name = f"{new_name}_{data.name[len(prefix):]}"
                data.name = name
                view.name = f"{new_name}.{name}"

    def _studio_rename_group_refs(self, renamed):
        """Rewrite the « groups » attribute of every set_attribute change of
        the project that names one of ``renamed`` ({former external id: new
        external id}), a leading « ! » kept, in its value and in its
        « groups ». The changed payload puts the project back in draft: the
        next Apply writes the new external ids into the views, and the
        generation copies them."""
        self.ensure_one()
        if not renamed:
            return
        for change in self.change_ids.filtered(
            lambda c: c.change_type == "set_attribute"
        ):
            payload = change._payload()
            if not set(payload.get("groups") or ()) & set(renamed):
                continue
            items = []
            for item in (payload.get("value") or "").split(","):
                negated = "!" if item.startswith("!") else ""
                xmlid = item[len(negated) :]
                items.append(negated + renamed.get(xmlid, xmlid))
            payload["value"] = ",".join(items)
            payload["groups"] = [renamed.get(x, x) for x in payload["groups"]]
            change.sudo()._set_payload(payload)

    # ── records under external ids of the module ────────────────────────

    def _studio_record(self, res_model, name):
        """The record of ``res_model`` under the external id ``name`` of the
        module of the project, in sudo and without language (Apply writes
        the source terms), or an empty recordset."""
        Model = self.env[res_model].sudo().with_context(lang=None)
        if len(self) != 1 or not self.module_name:
            return Model
        data = (
            self.env["ir.model.data"]
            .sudo()
            .search(
                [
                    ("module", "=", self.module_name),
                    ("name", "=", name),
                    ("model", "=", res_model),
                ],
                limit=1,
            )
        )
        return Model.browse(data.res_id).exists()

    def _studio_bind(self, record, name):
        """Give ``record`` the external id ``name`` of the module, marked
        « noupdate »: when the generated module is installed in this
        database, an upgrade deletes every external id of the module that
        its files do not hold and is not « noupdate », with its record (a
        model goes with its table). What Apply creates after the last
        generation is in no file yet; a generation clears the mark of the
        ids it writes (erplibre_studio_generate)."""
        if not XML_NAME.match(name or ""):
            raise UserError(
                self.env._(
                    "%(name)s is not a valid external id: letters, digits, « _ » "
                    "and « - ».",
                    name=name,
                )
            )
        self.env["ir.model.data"].sudo().create(
            {
                "module": self.module_name,
                "name": name,
                "model": record._name,
                "res_id": record.id,
                "noupdate": True,
            }
        )

    @api.model
    def _studio_differences(self, record, vals):
        """The values of ``vals`` (create values) that ``record`` lacks."""
        todo = {}
        for key, value in vals.items():
            field = record._fields[key]
            current = record[key]
            if field.type == "many2one":
                current, value = current.id, value or False
            elif field.type in ("many2many", "one2many"):
                current = sorted(current.ids)
                value = sorted(value[0][2]) if value else []
            elif field.type == "reference":
                current = f"{current._name},{current.id}" if current else False
            elif key == "arch":
                current, value = normal_arch(current), normal_arch(value)
            elif field.type in ("char", "text", "html"):
                # The whitespace around a text is not part of it: a data
                # file may wrap a long value on lines of its own.
                current = (current or "").strip() or False
                value = (value or "").strip() or False
            if current != value:
                todo[key] = vals[key]
        return todo

    def _studio_save(self, res_model, name, vals, log, update=True):
        """The record of ``res_model`` under the external id ``name``,
        created from ``vals``, or written where it differs. ``update``
        False leaves an existing record as it is. Return (record, whether
        it differs from ``vals`` and was left as it is)."""
        record = self._studio_record(res_model, name)
        if not record:
            record = self.env[res_model].sudo().with_context(lang=None).create(vals)
            self._studio_bind(record, name)
            log.append(f"{res_model} {name}: created")
            return record, False
        todo = self._studio_differences(record, vals)
        if todo and update:
            record.write(todo)
            log.append(f"{res_model} {name}: updated")
        return record, bool(todo) and not update

    def _field_vals(self, model, name, definition):
        """The ir.model.fields values of the definition ``definition``. Each
        option of FIELD_OPTIONS its type takes is written, False or 0 when
        the definition leaves it out: a field applied without the options
        shows no difference."""
        vals = {
            "field_description": definition["field_description"],
            "readonly": definition.get("readonly", False),
            "help": definition.get("help") or False,
        }
        ttype = definition["ttype"]
        if ttype in FIELD_OPTIONS["translate"]:
            vals["translate"] = bool(definition.get("translate"))
        if ttype in FIELD_OPTIONS["index"]:
            vals["index"] = bool(definition.get("index"))
        if ttype in FIELD_OPTIONS["size"]:
            vals["size"] = int(definition.get("size") or 0)
        if ttype == "selection":
            vals["selection"] = repr([tuple(item) for item in definition["selection"]])
        elif ttype == "many2one":
            vals["relation"] = definition["relation"]
            vals["on_delete"] = definition.get("on_delete") or "set null"
        elif ttype == "one2many":
            vals["relation"] = definition["relation"]
            vals["relation_field"] = definition["relation_field"]
        elif ttype == "many2many":
            vals["relation"] = definition["relation"]
            for key in ("relation_table", "column1", "column2"):
                vals[key] = definition[key]
        elif ttype == "monetary":
            vals["currency_field"] = definition["currency_field"]
        # A geometry field (GEO_TYPES) writes none of the srid, geo_type and
        # dim columns base_geoengine adds: a manual field is built with the
        # defaults of its class (srid 3857, 2 dimensions, a GiST index),
        # whatever those columns hold.
        return vals

    def _apply_fields(self, log):
        """Create or update the new fields of the project, in the order of
        ``_studio_all_definitions``. Return (fields kept, names of the fields
        whose new definition waits for the module): a field the generated
        module defines, once installed, changes with the module only.
        UserError on a field to create without ``x_`` while the rule of the
        database (``_studio_field_name_rule``, read on each call) requires
        it."""
        Fields = self.env["ir.model.fields"].sudo()
        kept = Fields
        waiting = []
        prefix_required = self._studio_field_name_rule()["prefix_required"]
        for model, name, definition, _change in self._studio_all_definitions():
            vals = self._field_vals(model, name, definition)
            field = Fields._get(model, name)
            if not field:
                if prefix_required and not (name or "").startswith("x_"):
                    # The SQL constraint of ir.model.fields would refuse it
                    # with an IntegrityError instead.
                    raise UserError(
                        self.env._(
                            "%(name)s needs the x_ prefix on this database.",
                            name=name,
                        )
                    )
                vals.update(
                    {
                        "name": name,
                        "model": model,
                        "model_id": self.env["ir.model"]._get_id(model),
                        "ttype": definition["ttype"],
                        "state": "manual",
                    }
                )
                field = Fields.create(vals)
                log.append(f"field {model}.{name}: created")
            elif field.state == "manual":
                if field.ttype != definition["ttype"]:
                    raise UserError(
                        self.env._(
                            "The field %(name)s exists with another type.",
                            name=name,
                        )
                    )
                todo = self._field_differences(field, vals)
                if set(todo) & RELATION_VALUES:
                    raise UserError(
                        self.env._(
                            "The relation of the field %(name)s cannot change.",
                            name=f"{model}.{name}",
                        )
                    )
                if todo:
                    field.write(todo)
                    log.append(f"field {model}.{name}: updated")
            elif self._module_of("ir.model.fields", field.id) == self.module_name:
                if self._field_differences(field, vals):
                    waiting.append(f"{model}.{name}")
                    log.append(
                        f"field {model}.{name}: defined by the module, "
                        "changes with its next generation and upgrade"
                    )
            else:
                log.append(f"field {model}.{name}: owned by a module, left as is")
            kept |= field
        return kept, waiting

    @api.model
    def _module_of(self, model_name, res_id):
        """The module of the first external id of the record ``res_id`` of
        ``model_name``, or False."""
        data = (
            self.env["ir.model.data"]
            .sudo()
            .search(
                [("model", "=", model_name), ("res_id", "=", res_id)],
                order="id",
                limit=1,
            )
        )
        return data.module or False

    @api.model
    def _field_differences(self, field, vals):
        """The values of ``vals`` (``_field_vals``) that ``field`` lacks."""
        current = {k: field[k] for k in vals if k != "selection"}
        if "selection" in vals:
            current["selection"] = repr(
                [(s.value, s.name) for s in field.selection_ids]
            )
        return {k: v for k, v in vals.items() if current.get(k) != v}

    def _apply_views(self, log):
        View = self.env["ir.ui.view"].sudo()
        kept = View
        for view in self.change_ids.mapped("view_id"):
            changes = [c._as_dict() for c in self._view_changes(view)]
            vals = {
                "name": f"{self.module_name}.{self._studio_xmlname(view)}",
                "model": view.model,
                "inherit_id": view.id,
                "mode": "extension",
                "priority": STUDIO_PRIORITY,
                "arch": studio_arch.view_arch(changes, view.type),
            }
            studio_view = self._studio_view(view)
            if studio_view:
                studio_view.write(vals)
                log.append(f"view {vals['name']}: updated")
            else:
                studio_view = View.create(vals)
                self._studio_bind(studio_view, self._studio_xmlname(view))
                log.append(f"view {vals['name']}: created")
            kept |= studio_view
        return kept

    def _studio_check_apply(self):
        """The checks of the lines again, before Apply writes anything: the
        parent menus, groups and models the lines name leave the database
        with the module that defines them. Raise UserError on the first
        line that does not apply; each check of a line is its own method,
        which the review runs line by line."""
        self.ensure_one()
        refusal = self._studio_foreign_model_refusal()
        if refusal:
            raise UserError(refusal)
        mail = self._studio_mail_available()
        for line in self.new_model_ids:
            self._studio_check_apply_model(line, mail)
        for line in self.access_line_ids:
            self._studio_check_apply_access(line)
        self._studio_check_apply_rules()
        self._studio_check_apply_groups()
        for change in self.change_ids:
            self._studio_check_apply_change(change)
        for line in self.view_line_ids:
            self._studio_check_apply_view(line)
        self._studio_check_relations()
        names = self._studio_new_models()
        self._studio_check_model_removal(
            self.created_model_ids.exists().filtered(lambda m: m.model not in names)
        )

    def _studio_check_apply_model(self, line, mail):
        """Raise UserError when the model line ``line`` does not apply: its
        menu, its chatter without mail (``mail``: whether mail is
        installed), a model of that name already in the database, no access
        row on it, a field of an option turned off that cannot leave
        (``_studio_option_removal_refusal``), a default order on a field the
        model will not have."""
        self.ensure_one()
        self._studio_check_menu(line)
        if line.chatter and not mail:
            raise UserError(self.env._("A chatter needs the module mail (Discuss)."))
        if line.model in self.env and not line.applied:
            raise UserError(
                self.env._("The model %(name)s already exists.", name=line.model)
            )
        if not line.applied:
            # A draft line recorded under another rule, or whose name a
            # model, a table or a module took since.
            status = self._studio_model_name_status(line.model, line)
            if status["code"]:
                raise UserError(status["message"])
        if line.model not in self.access_line_ids.mapped("model"):
            # Without one, the model is the superuser's only, and the
            # generated module has no access file.
            raise UserError(
                self.env._(
                    "The model %(name)s needs at least one access right.",
                    name=line.model,
                )
            )
        fields_, _waiting = self._studio_option_removals(line)
        refusal = self._studio_option_removal_refusal(fields_)
        if refusal:
            raise UserError(refusal)
        if line.order:
            sortable = self._studio_sortable_fields(line)
            for name in studio_arch.order_fields(line.order):
                if name not in sortable:
                    raise UserError(
                        self.env._(
                            "The default order of %(model)s names %(name)s, "
                            "which the model will not have: choose another "
                            "order.",
                            model=line.model,
                            name=name,
                        )
                    )

    def _studio_check_apply_access(self, line):
        """Raise UserError when the access row ``line`` does not apply: its
        model, its group, the rights of a share group, its external id."""
        self.ensure_one()
        self._studio_check_rights_model(line.model)
        if line.group_line_id:
            if line.group_line_id.project_id != self:
                raise UserError(
                    self.env._(
                        "The access row on %(model)s names a group of "
                        "another project.",
                        model=line.model,
                    )
                )
        else:
            self._studio_check_group(line.group_id)
        self._studio_check_access_line(line)
        if line.xml_name != line._studio_xml_name():
            raise UserError(
                self.env._(
                    "The access row on %(model)s has the external id "
                    "%(name)s instead of %(expected)s.",
                    model=line.model,
                    name=line.xml_name,
                    expected=line._studio_xml_name(),
                )
            )

    def _studio_check_apply_change(self, change):
        """Raise UserError when ``change`` is on no view of the project (a
        change of a model line of another project), or when a new field it
        adds has a technical name that does not apply
        (``_studio_field_name_problem``, the field itself aside)."""
        self.ensure_one()
        line = change.model_line_id or change.view_line_id
        if not change.view_id and line.project_id != self:
            raise UserError(
                self.env._(
                    "The change « %(change)s » is on no view of the project.",
                    change=change.summary,
                )
            )
        if change.change_type != "add_field":
            return
        for model, name in self._studio_change_field_names(change):
            problem = self._studio_field_name_problem(model, name, own=name)
            if problem:
                raise UserError(
                    self.env._(
                        "The technical name %(name)s does not apply: %(message)s",
                        name=name,
                        message=problem["message"],
                    )
                )

    def _studio_check_apply_view(self, line):
        """Raise UserError when the view line ``line`` does not apply: its
        model left the database, the studio no longer edits its type, or
        another view of its type is now the default of the model. A model
        line of the project creates its model again before Apply creates the
        added views: a view added to it is not refused while the model is
        out of the database (after Revert or an uninstall)."""
        self.ensure_one()
        label = (
            self.env["erplibre.studio.editor"]
            ._view_type_labels()
            .get(line.view_type, line.view_type)
        )
        if line.model not in self.env and line.model not in self._studio_new_models():
            raise UserError(
                self.env._(
                    "The model %(model)s of the %(type)s view the project adds "
                    "left the database.",
                    model=line.model,
                    type=label,
                )
            )
        if line.view_type not in self._view_types():
            raise UserError(
                self.env._("The studio does not edit %(type)s views.", type=label)
            )
        View = self.env["ir.ui.view"].sudo()
        default = View.browse(View.default_view(line.model, line.view_type))
        if default and default != line.view_id:
            raise UserError(
                self.env._(
                    "%(model)s has a %(type)s view now (%(view)s): remove the "
                    "one the project adds.",
                    model=line.model,
                    type=label,
                    view=default.xml_id or default.name,
                )
            )
        if line.view_type == "leaflet_map":
            self._studio_check_leaflet_coordinates(line)
            self._studio_check_leaflet_date(line)

    def _studio_check_leaflet_date(self, line):
        """Raise UserError when the model of the map of the view line
        ``line`` has no LEAFLET_DATE_FIELD and the project does not create
        it: the map reads it with every marker, and the read fails without
        it. An undo or a removal of the field the map creates leads there."""
        name = studio_arch.LEAFLET_DATE_FIELD
        if line.model not in self.env or name in self.env[line.model]._fields:
            return
        if self._field_add_change(line.model, name):
            return
        raise UserError(
            self.env._(
                "The map %(view)s reads a %(field)s field that %(model)s does "
                "not have: remove the map and add it again to create it.",
                view=line._studio_view_name(),
                field=name,
                model=line.model,
            )
        )

    def _studio_check_leaflet_coordinates(self, line):
        """Raise UserError when the map of the view line ``line``, with the
        changes of the draft, has no latitude or no longitude field: the
        map places no marker without both."""
        view = line.view_id if line.applied and line.view_id else added_view(line)
        arch, _errors = self._draft_arch(view)
        if not all(
            arch.get(attribute)
            for attribute in studio_arch.REQUIRED_ATTRIBUTES[
                ("leaflet_map", "leaflet_map")
            ]
        ):
            raise UserError(
                self.env._(
                    "The map %(view)s needs a latitude and a longitude field.",
                    view=line._studio_view_name(),
                )
            )

    def _studio_check_apply_rules(self):
        """The checks of the rule lines before Apply
        (``_studio_check_apply_rule``)."""
        self.ensure_one()
        for rule in self.rule_line_ids:
            self._studio_check_apply_rule(rule)

    def _studio_check_apply_rule(self, rule):
        """Raise UserError when the rule line ``rule`` does not apply: the
        groups it names, a group or « Global », and its domain on an
        existing model."""
        self.ensure_one()
        self._studio_check_rights_model(rule.model)
        for group in rule.group_ids:
            self._studio_check_group(group)
        rule._check_studio_xml_name()
        missing = rule._studio_missing_group_refs()
        if missing:
            raise UserError(
                self.env._(
                    "The rule %(name)s lost the groups %(groups)s: choose its "
                    "groups again.",
                    name=rule.name,
                    groups=", ".join(missing),
                )
            )
        self._studio_check_global_rule(rule)
        if not (rule.group_ids or rule.group_line_ids or rule.global_rule):
            raise UserError(
                self.env._(
                    "The rule %(name)s has no group: check « Global » to "
                    "apply it to every user, or choose its groups.",
                    name=rule.name,
                )
            )
        if rule.group_line_ids - self.group_line_ids:
            raise UserError(
                self.env._(
                    "The rule %(name)s names a group of another project.",
                    name=rule.name,
                )
            )
        if rule.model in self.env:
            self._studio_check_rule(rule)

    def _studio_check_apply_groups(self):
        """The checks of the apps and the groups before Apply."""
        self.ensure_one()
        for app in self.app_ids:
            app._check_studio_app()
        for group in self.group_line_ids:
            self._studio_check_apply_group(group)

    def _studio_check_apply_group(self, group):
        """Raise UserError when the group line ``group`` does not apply: its
        constraints, an implied group it lost."""
        self.ensure_one()
        group._check_studio_group()
        missing = group._studio_missing_implied_refs()
        if missing:
            raise UserError(
                self.env._(
                    "The group %(name)s lost the implied groups %(groups)s: "
                    "choose them again.",
                    name=group.name,
                    groups=", ".join(missing),
                )
            )

    def _model_vals(self, line, label):
        """The ir.model values of the custom model of the model line
        ``line`` labelled ``label``: its name, its ``x_name`` and, with the
        chatter, the mail flags."""
        vals = {
            "model": line.model,
            "name": label,
            "state": "manual",
            "field_id": [
                Command.create(
                    {
                        "name": "x_name",
                        "field_description": "Name",
                        "ttype": "char",
                        "required": True,
                        "copied": True,
                    }
                )
            ],
        }
        if line.chatter:
            vals.update(is_mail_thread=True, is_mail_activity=True)
        return vals

    def _apply_models(self, log):
        """Create or update the custom models of the model lines, with their
        ``x_name``. Return (models kept, names of the models whose new label
        or chatter waits for the module): a model the generated module
        defines, once installed, changes with the module only. UserError
        on a model to create without ``x_`` while the rule of the database
        (``_studio_model_name_rule``, read on each call) requires it."""
        IrModel = self.env["ir.model"].sudo().with_context(lang=None)
        kept = IrModel
        waiting = []
        mail = self._studio_mail_available()
        prefix_required = self._studio_model_name_rule()["prefix_required"]
        for line in self.new_model_ids:
            name = line._studio_xml_names()["model"]
            label = line.name.strip()
            record = self._studio_record("ir.model", name)
            if not record:
                if IrModel._get_id(line.model):
                    raise UserError(
                        self.env._(
                            "The model %(name)s already exists.", name=line.model
                        )
                    )
                if prefix_required and not line.model.startswith("x_"):
                    # ir.model would refuse it with a ValidationError on
                    # the core rule instead.
                    raise UserError(
                        self.env._(
                            "%(name)s needs the x_ prefix on this database.",
                            name=line.model,
                        )
                    )
                record = IrModel.create(self._model_vals(line, label))
                self._studio_bind(record, name)
                log.append(f"model {line.model}: created")
                kept |= record
                continue
            todo = {}
            if record.name != label:
                todo["name"] = label
            if mail and line.chatter and not record.is_mail_thread:
                todo.update(is_mail_thread=True, is_mail_activity=True)
            elif mail and not line.chatter and record.is_mail_thread:
                raise UserError(
                    self.env._(
                        "The chatter of %(name)s cannot be removed once applied.",
                        name=line.model,
                    )
                )
            if record.state != "manual":
                if todo:
                    waiting.append(line.model)
                    log.append(
                        f"model {line.model}: defined by the module, changes "
                        "with its next generation and upgrade"
                    )
            elif todo:
                record.write(todo)
                log.append(f"model {line.model}: updated")
            kept |= record
        return kept, waiting

    def _apply_model_options(self, log, owned):
        """Give each custom model of the model lines the fields of its
        options and its default order, after the new fields: the order may
        name one of them, and ir.model checks it against the stored fields.
        A field of an option is created with its constant default
        (ir.default, which leaves with the field; ``x_company_id`` takes its
        company from the window action instead), on a model the installed
        module defines as well, as a new field of the project is: the next
        generation writes it into the module; ``x_active`` created on a
        model that has records marks them active, as a new column is empty
        and an empty ``x_active`` reads as archived. The fields of the
        options are not counted among the fields of the project: they leave
        with the model, as ``x_name``. The order of a model in ``owned``,
        defined by the installed module, changes with the module only.
        Return the names of the models whose order waits for the module."""
        IrModel = self.env["ir.model"].sudo().with_context(lang=None)
        Fields = self.env["ir.model.fields"].sudo().with_context(lang=None)
        Default = self.env["ir.default"].sudo()
        waiting = []
        for line in self.new_model_ids:
            record = IrModel._get(line.model)
            if not record:
                continue
            defaults = line._studio_option_defaults()
            for name, field_vals in line._studio_option_field_vals().items():
                if Fields._get(line.model, name):
                    continue
                Fields.create(
                    dict(
                        field_vals,
                        model=line.model,
                        model_id=record.id,
                        state="manual",
                    )
                )
                log.append(f"field {line.model}.{name}: created")
                if name in defaults:
                    Default.set(line.model, name, defaults[name])
                if field_vals["ttype"] == "boolean":
                    Model = self.env[line.model].sudo().with_context(active_test=False)
                    Model.search([(name, "=", False)]).write({name: True})
            order = line.order or "id"
            if record.order == order:
                continue
            if line.model in owned:
                waiting.append(line.model)
                log.append(
                    f"model {line.model}: order defined by the module, changes "
                    "with its next generation and upgrade"
                )
            else:
                record.write({"order": order})
                log.append(f"model {line.model}: order {order}")
        return waiting

    # ── options removed after Apply ─────────────────────────────────────

    def _studio_applied_model_item(self, model):
        """The entry of the model line of ``model`` in the snapshot of the
        last Apply ({} when none)."""
        self.ensure_one()
        snapshot = self._studio_load_snapshot(self.applied_snapshot)
        for item in snapshot["models"]:
            if item.get("model") == model:
                return item
        return {}

    def _studio_option_own_field(self, line, key, item=None):
        """The field (ir.model.fields, sudo) of the option ``key`` of the
        model line ``line`` on its applied model when it is the option's
        own: the last Apply had the option on (``item``, its entry in the
        snapshot, read when None), or the generated module defines the
        field. Empty for a field of the same name made otherwise, which
        no option removes."""
        self.ensure_one()
        Fields = self.env["ir.model.fields"].sudo()
        if not line.applied:
            return Fields
        name = studio_arch.MODEL_OPTIONS[key][0]
        field = Fields._get(line.model, name)
        if not field:
            return Fields
        if item is None:
            item = self._studio_applied_model_item(line.model)
        if item.get(key):
            return field
        if field.state != "manual" and (
            self._module_of("ir.model.fields", field.id) == self.module_name
        ):
            return field
        return Fields

    def _studio_option_leaving(self, line):
        """{option: field} of the options of the applied model line ``line``
        that are off while their own field (``_studio_option_own_field``)
        is still on the model: the next Apply removes these fields, or,
        on a model the installed generated module defines, leaves them to
        its next generation and upgrade."""
        self.ensure_one()
        if not line.applied:
            return {}
        item = self._studio_applied_model_item(line.model)
        definitions = self._studio_field_definitions(line.model)
        leaving = {}
        for key, (name, _ttype, _label) in studio_arch.MODEL_OPTIONS.items():
            if line[key] or name in definitions:
                continue
            field = self._studio_option_own_field(line, key, item)
            if field:
                leaving[key] = field
        return leaving

    @api.model
    def _studio_option_waits(self, line, field):
        """Whether the removal of the field of an option ``field`` of the
        model line ``line`` waits for the generated module: the module
        defines the model or the field, and only its upgrade drops them."""
        return field.state != "manual" or line.ir_model_id.sudo().state != "manual"

    def _studio_option_removals(self, lines=None):
        """(fields, waiting) of the options turned off after Apply on the
        model lines ``lines`` (default: all of them): the ir.model.fields
        (sudo) the next Apply removes, after it rewrote the default views,
        the window action, the order and the rules without them; and the
        « model.field » names whose removal waits for the installed
        generated module (``_studio_option_waits``)."""
        self.ensure_one()
        fields_ = self.env["ir.model.fields"].sudo()
        waiting = []
        for line in self.new_model_ids if lines is None else lines:
            for field in self._studio_option_leaving(line).values():
                if self._studio_option_waits(line, field):
                    waiting.append(f"{line.model}.{field.name}")
                else:
                    fields_ |= field
        return fields_, waiting

    def _studio_option_removal_refusal(self, fields_, rules=None, rule_lines=None):
        """Why ``fields_`` (fields of options) cannot leave the database
        now, or False. ``rules``: the ir.rule that leave with them
        (default: those the next Apply removes); ``rule_lines``: the rule
        lines of the project that leave with them. What the project
        rewrites at Apply is judged by its draft: its rules by their rule
        lines, its inherited views by its changes, the default views of
        its models and the views its view lines add by their new arch.
        Refused while a record rule or a change names a field
        (``_studio_check_field_removal``), a custom field depends on it,
        or a view of its model, or a rule line of the project, names it:
        ir.model.fields would refuse the removal in the middle of Apply."""
        self.ensure_one()
        if not fields_:
            return False
        _ = self.env._
        Rule = self.env["ir.rule"].sudo()
        if rules is None:
            rules = self._studio_apply_removals().get("rules", Rule)
        rule_lines = self.rule_line_ids - (
            rule_lines or self.env["erplibre.studio.rule"]
        )
        own_rules = Rule
        for rule_line in self.rule_line_ids:
            own_rules |= self._studio_record("ir.rule", rule_line.xml_name)
        messages = []
        try:
            self._studio_check_field_removal(
                fields_, rules | own_rules, self.change_ids
            )
        except UserError as exc:
            messages.append(exc.args[0])
        rewritten = self.studio_view_ids | self.view_line_ids.view_id
        for line in self.new_model_ids:
            for view in line._studio_views().values():
                rewritten |= view
        for field in fields_.sorted(lambda f: (f.model, f.name)):
            items = self._studio_option_field_uses(field, rule_lines, rewritten)
            if items:
                messages.append(
                    _(
                        "The field %(field)s cannot be removed, it is still "
                        "used: %(items)s.",
                        field=f"{field.model}.{field.name}",
                        items=", ".join(sorted(set(items))),
                    )
                )
        return " ".join(messages) or False

    def _studio_option_field_uses(self, field, rule_lines, rewritten):
        """The descriptions of what still names ``field`` (an ir.model.fields
        of an option) once Apply rewrote what the project owns: the custom
        fields that depend on it or are its one2many inverse, the rule
        lines ``rule_lines`` whose domain names it, the views of its model
        but ``rewritten`` whose arch names it, and the view lines of the
        project whose arch names it."""
        _ = self.env._
        items = []
        pattern = re.compile(rf"(?<!\w){re.escape(field.name)}(?!\w)")
        Model = self.env.get(field.model)
        odoo_field = Model._fields.get(field.name) if Model is not None else None
        if odoo_field is not None:
            dependents = [
                dep for dep in self.pool.get_dependent_fields(odoo_field) if dep.manual
            ] + [
                inverse
                for inverse in self.pool.field_inverses[odoo_field]
                if inverse.manual and inverse.type == "one2many"
            ]
            items += [
                _("the field %(name)s depends on it", name=str(dep))
                for dep in dependents
            ]
        for rule_line in rule_lines.filtered(lambda r: r.model == field.model):
            named = self._studio_domain_fields(rule_line.model, rule_line.domain_force)
            if (field.model, field.name) in named:
                items.append(_("the rule %(name)s of the project", name=rule_line.name))
        View = self.env["ir.ui.view"].sudo().with_context(active_test=False)
        views = (
            View.search([("model", "=", field.model), ("arch_db", "ilike", field.name)])
            - rewritten
        )
        for view in views:
            if pattern.search(view.with_context(lang=None).arch_db or ""):
                items.append(_("the view %(name)s", name=view.name))
        for view_line in self.view_line_ids.filtered(lambda v: v.model == field.model):
            if pattern.search(view_line.arch or ""):
                items.append(
                    _(
                        "the view %(name)s of the project",
                        name=view_line._studio_view_name(),
                    )
                )
        return items

    def _studio_option_removal_report(self, line, key):
        """{report, refused, waiting} of turning the option ``key`` of the
        model line ``line`` off now: what the next Apply removes with it
        (``_studio_removal_report`` of its own field and, for « Per
        company », of the applied rule of its rule line, with the effects
        on the records), why the removal is refused (or False), and
        whether the removal waits for the installed generated module: the
        report then lists what its upgrade removes, which Apply leaves to
        it. A read."""
        self.ensure_one()
        Fields = self.env["ir.model.fields"].sudo()
        Rule = self.env["ir.rule"].sudo()
        field = self._studio_option_own_field(line, key)
        waiting = bool(field) and self._studio_option_waits(line, field)
        removable = Fields if waiting else field
        rules = Rule
        rule_lines = self.env["erplibre.studio.rule"]
        if key == "per_company" and line.company_rule_id:
            rule_lines = line.company_rule_id
            rules = self._studio_record("ir.rule", rule_lines.xml_name)
        report = self._studio_removal_report(
            {
                "fields": removable,
                "module_fields": field if waiting else Fields,
                "rules": rules,
            }
        )
        leaving = self._studio_apply_removals().get("rules", Rule) | rules
        return {
            "report": report,
            "refused": self._studio_option_removal_refusal(
                removable, leaving, rule_lines
            ),
            "waiting": waiting,
        }

    def _apply_model_views(self, log, owned):
        """Create or update the default form, list and search views of the
        model lines. Those of the models in ``owned``, defined by the
        installed module, are left as they are. Return (views kept, names
        of the views waiting for the module)."""
        kept = self.env["ir.ui.view"].sudo()
        waiting = []
        for line in self.new_model_ids:
            names = line._studio_xml_names()
            for view_type in studio_arch.MODEL_VIEW_TYPES:
                vals = {
                    "name": f"{line.model}.{view_type}",
                    "model": line.model,
                    "type": view_type,
                    "mode": "primary",
                    "priority": MODEL_VIEW_PRIORITY,
                    "arch": self._studio_default_arch(line, view_type),
                }
                view, differs = self._studio_save(
                    "ir.ui.view",
                    names[view_type],
                    vals,
                    log,
                    update=line.model not in owned,
                )
                if differs:
                    waiting.append(vals["name"])
                elif line.archivable and line.model not in owned:
                    self._studio_translate_archived(view)
                kept |= view
        return kept, waiting

    def _studio_translate_archived(self, view):
        """Give the term « Archived » of the option « archivable » (the
        ribbon of the form, the filter of the search view) of ``view`` its
        text in each installed language, from the catalogue of the studio:
        Apply writes the source terms of the arch."""
        source = "Archived"
        if source not in (view.with_context(lang=None).arch_db or ""):
            return
        translations = {}
        for code, _name in self.env["res.lang"].get_installed():
            text = self.with_context(lang=code).env._("Archived")
            if code != "en_US" and text != source:
                translations[code] = {source: text}
        if translations:
            view.update_field_translations("arch_db", translations)

    def _apply_added_views(self, log):
        """Create the views the view lines add, primary, with the arch each
        line recorded: the only view of its type on its model, its default
        one. Return the views kept."""
        kept = self.env["ir.ui.view"].sudo()
        for line in self.view_line_ids:
            view, _differs = self._studio_save(
                "ir.ui.view",
                line._studio_xml_name(),
                {
                    "name": line._studio_view_name(),
                    "model": line.model,
                    "type": line.view_type,
                    "mode": "primary",
                    "priority": MODEL_VIEW_PRIORITY,
                    "arch": line.arch,
                },
                log,
            )
            kept |= view
        return kept

    def _studio_geo_layer_records(self):
        """{kind of GEO_LAYER_KINDS: records} of the layers under external
        ids of the module of the project, for the layer models of the
        database (none without base_geoengine)."""
        Data = self.env["ir.model.data"].sudo()
        records = {}
        for kind, res_model in GEO_LAYER_KINDS.items():
            if res_model not in self.env:
                continue
            Model = self.env[res_model].sudo()
            if len(self) != 1 or not self.module_name:
                records[kind] = Model
                continue
            data = Data.search(
                [("module", "=", self.module_name), ("model", "=", res_model)]
            )
            records[kind] = Model.browse(data.mapped("res_id")).exists()
        return records

    def _apply_geo_layers(self, log):
        """Write the layers of the GeoEngine views the view lines add to
        base_geoengine, bound to the view Apply created for their line.
        A vector layer names its geo field by its ir.model.fields, which
        Apply created before. Return {kind of GEO_LAYER_KINDS: the layers
        kept}; UserError when a layer draws a field the model lacks."""
        kept = {
            kind: self.env[res_model].sudo()
            for kind, res_model in GEO_LAYER_KINDS.items()
            if res_model in self.env
        }
        if not kept:
            return kept
        Fields = self.env["ir.model.fields"].sudo()
        kinds = {res_model: kind for kind, res_model in GEO_LAYER_KINDS.items()}
        for line in self.view_line_ids.filtered("layer_ids"):
            view = self._studio_record("ir.ui.view", line._studio_xml_name())
            if not view:
                continue
            for layer in line.layer_ids:
                vals = {
                    "name": layer.name,
                    "sequence": layer.sequence,
                    "view_id": view.id,
                }
                if layer.kind == "raster":
                    vals["raster_type"] = layer.raster_type or "osm"
                else:
                    geo_field = Fields._get(line.model, layer.geo_field)
                    if not geo_field:
                        raise UserError(
                            self.env._(
                                "The layer %(layer)s draws the field %(field)s, "
                                "which %(model)s does not have.",
                                layer=layer.name,
                                field=layer.geo_field,
                                model=line.model,
                            )
                        )
                    vals.update(
                        {
                            "geo_field_id": geo_field.id,
                            "geo_repr": layer.geo_repr or "basic",
                            "attribute_field_id": Fields._get(
                                line.model, layer.attribute_field or ""
                            ).id,
                            "classification": layer.classification or False,
                            "begin_color": layer.begin_color or False,
                            "end_color": layer.end_color or False,
                            "nb_class": layer.nb_class or 1,
                            "active_on_startup": layer.active_on_startup,
                        }
                    )
                res_model = layer._studio_layer_model()
                record, _differs = self._studio_save(
                    res_model, layer._studio_xml_name(), vals, log
                )
                kept[kinds[res_model]] |= record
        return kept

    def _apply_actions(self, log):
        """Create or update the window action of each model line, with the
        context of its options (``_studio_action_context``) and the views
        the project adds to its model (``_studio_view_mode``)."""
        kept = self.env["ir.actions.act_window"].sudo()
        for line in self.new_model_ids:
            names = line._studio_xml_names()
            search = self._studio_record("ir.ui.view", names["search"])
            action, _differs = self._studio_save(
                "ir.actions.act_window",
                names["action"],
                {
                    "name": line.name.strip(),
                    "res_model": line.model,
                    "view_mode": line._studio_view_mode(),
                    "search_view_id": search.id,
                    "context": line._studio_action_context() or "{}",
                },
                log,
            )
            kept |= action
        return kept

    def _studio_module_icon(self, app):
        """The icon of the menu of ``app`` in the installed generated module:
        « <module>,static/description/<app external id>.png », the copy of
        the chosen icon the generation writes into the module; None while
        the module is not installed or does not hold that file (an app added
        since the last generation, a module generated before the apps had
        their own icon)."""
        self.ensure_one()
        if self.module_state != "installed":
            return None
        path = app._studio_xml_names()["icon_path"]
        try:
            file_path(f"{self.module_name}/{path}")
        except (FileNotFoundError, ValueError):
            return None
        return f"{self.module_name},{path}"

    def _studio_app_web_icon(self, app):
        """The ``web_icon`` Apply gives the menu of ``app``: once the
        generated module is installed with the icon of the app, the icon of
        the module, which owns the menu; else the chosen icon, or the
        studio's."""
        self.ensure_one()
        return self._studio_module_icon(app) or app.icon or DEFAULT_APP_ICON

    def _studio_generated_icon(self, app):
        """The icon ``app`` had at the last generation of the module, or None
        when unknown: then the icon counts as generated. The generation
        records it (erplibre_studio_generate)."""
        return None

    def _apply_menus(self, log):
        """Create or update the top-level menu of each app a model goes in,
        and the menu of each model line, on its window action, in its app or
        under its parent menu. Return (menus kept, names of the app icons that wait
        for the next generation of the installed module)."""
        kept = self.env["ir.ui.menu"].sudo()
        waiting = []
        apps = {}
        for app in self.app_ids.filtered(lambda a: a._studio_menu_models()):
            menu, _differs = self._studio_save(
                "ir.ui.menu",
                app.xml_name,
                {
                    "name": app.name.strip(),
                    "web_icon": self._studio_app_web_icon(app),
                    "sequence": app.menu_sequence,
                    "parent_id": False,
                    "action": False,
                },
                log,
            )
            if self.module_state == "installed":
                generated = self._studio_generated_icon(app)
                if self._studio_module_icon(app) is None or (
                    generated is not None
                    and (app.icon or False) != (generated or False)
                ):
                    waiting.append(self.env._("app icon %(name)s", name=app.name))
            apps[app] = menu
            kept |= menu
        for line in self.new_model_ids:
            names = line._studio_xml_names()
            action = self._studio_record("ir.actions.act_window", names["action"])
            if line.menu_mode == "app":
                parent = apps.get(line.app_id, kept.browse())
            else:
                parent = line.menu_parent_id
            menu, _differs = self._studio_save(
                "ir.ui.menu",
                names["menu"],
                {
                    "name": (line.menu_name or "").strip() or line.name.strip(),
                    "parent_id": parent.id,
                    "action": f"{action._name},{action.id}",
                    "sequence": line.menu_sequence,
                },
                log,
            )
            kept |= menu
        return kept, waiting

    def _apply_categories(self, log):
        """Create or update the category of each app that has groups: the
        block of its groups in the user form, under « Other »."""
        kept = self.env["ir.module.category"].sudo()
        for app in self.app_ids.filtered("group_line_ids"):
            category, _differs = self._studio_save(
                "ir.module.category",
                app._studio_xml_names()["category"],
                {"name": app.name.strip(), "sequence": app.menu_sequence},
                log,
            )
            kept |= category
        return kept

    def _studio_group_losses(self):
        """[(record, dropped, users)]: for each res.groups of a group of the
        project, each res.groups of another group of the project it implies
        now and no longer implies in the draft, and the members who lose
        ``dropped`` once Apply writes the implications of the draft: those
        none of whose other groups implies it then, directly or not (as
        ``res.groups._remove_group`` decides). Odoo adds the members of a
        group to the groups it comes to imply, never takes them out of those
        it stops implying. An existing group a project group stops implying
        stays with its members: the studio takes no existing group from a
        user. A read."""
        self.ensure_one()
        Groups = self.env["res.groups"].sudo().with_context(active_test=False)
        records = {}
        future = {}
        for line in self.group_line_ids:
            record = line._studio_group_record()
            if not record:
                continue
            implied = line.implied_group_ids | line.implied_line_ids.mapped(
                lambda other: other._studio_group_record()
            )
            records[line] = record
            future[record.id] = set(implied.ids)
        own = Groups.browse(list(future))
        closures = {}

        def closure(group_id):
            """The groups ``group_id`` implies after Apply, directly or not."""
            if group_id not in closures:
                todo = set(
                    future.get(group_id, Groups.browse(group_id).implied_ids.ids)
                )
                found = set()
                while todo:
                    current = todo.pop()
                    if current in found:
                        continue
                    found.add(current)
                    todo |= set(
                        future.get(current, Groups.browse(current).implied_ids.ids)
                    )
                closures[group_id] = found
            return closures[group_id]

        losses = []
        for record in records.values():
            dropped_groups = record.implied_ids.filtered(
                lambda g, r=record: g.id not in future[r.id]
            )
            for dropped in dropped_groups & own:
                users = (record.users & dropped.users).filtered(
                    lambda u, d=dropped: not any(
                        d.id in closure(g) for g in (u.groups_id - d).ids
                    )
                )
                losses.append((record, dropped, users))
        return losses

    def _apply_groups(self, log):
        """Create or update the groups of the project, in the category of
        their app, then, once all exist, the groups each one implies; the
        members who got a group of the project only through an implication
        the draft drops lose it (``_studio_group_losses``)."""
        kept = self.env["res.groups"].sudo()
        for group in self.group_line_ids:
            category = self._studio_record(
                "ir.module.category", group.app_id._studio_xml_names()["category"]
            )
            record, _differs = self._studio_save(
                "res.groups",
                group.xml_name,
                {
                    "name": group.name.strip(),
                    "category_id": category.id,
                    "comment": group.comment or False,
                },
                log,
            )
            kept |= record
        losses = self._studio_group_losses()
        for group in self.group_line_ids:
            record = group._studio_group_record()
            implied = group.implied_group_ids | group.implied_line_ids.mapped(
                lambda line: line._studio_group_record()
            )
            todo = self._studio_differences(
                record, {"implied_ids": [(6, 0, implied.ids)]}
            )
            if todo:
                record.write(todo)
                log.append(f"res.groups {group.xml_name}: implied groups updated")
        for _record, dropped, users in losses:
            if users:
                dropped.with_context(active_test=False).write(
                    {"users": [Command.unlink(user.id) for user in users]}
                )
                log.append(f"res.groups {dropped.id}: {len(users)} member(s) removed")
        return kept

    def _studio_bind_pending_changes(self):
        """Bind the changes recorded on the default views of the new models,
        and on the views the view lines add, before Apply created them, to
        these views, now created: their node paths were recorded on the
        arch Apply gave them."""
        self.ensure_one()
        for change in self.change_ids.filtered("model_line_id"):
            view = change.model_line_id._studio_views().get(change.view_type)
            if view:
                change.with_context(**{NO_TOUCH_KEY: True}).sudo().write(
                    {"view_id": view.id, "model_line_id": False}
                )
        self.view_line_ids.invalidate_recordset(["applied", "view_id"])
        for change in self.change_ids.filtered("view_line_id"):
            view = change.view_line_id.view_id
            if view:
                change.with_context(**{NO_TOUCH_KEY: True}).sudo().write(
                    {"view_id": view.id, "view_line_id": False}
                )

    def _studio_unbind_added_changes(self, views):
        """Bind the changes on ``views``, views of view lines about to leave
        the database, back to their lines: the lines stay in the draft, and
        the paths of the changes hold on the arch the lines recorded.
        Return the changes bound back."""
        self.ensure_one()
        back = self.env["erplibre.studio.change"]
        for line in self.view_line_ids:
            record = line.view_id
            if not record or record not in views:
                continue
            changes = self.change_ids.filtered(lambda c, r=record: c.view_id == r)
            changes.with_context(**{NO_TOUCH_KEY: True}).sudo().write(
                {"view_id": False, "view_line_id": line.id}
            )
            back |= changes
        return back

    def _apply_access(self, log):
        """Create or update the ir.model.access of each access row, on an
        existing group or on a group of the project."""
        kept = self.env["ir.model.access"].sudo()
        IrModel = self.env["ir.model"]
        for line in self.access_line_ids:
            group = line.group_id or line.group_line_id._studio_group_record()
            if not group:
                # Without a group, an ir.model.access gives its rights to
                # every user.
                raise UserError(
                    self.env._(
                        "The access row on %(model)s names no group.",
                        model=line.model,
                    )
                )
            access, _differs = self._studio_save(
                "ir.model.access",
                line.xml_name,
                {
                    "name": line.xml_name,
                    "model_id": IrModel._get_id(line.model),
                    "group_id": group.id,
                    **{perm: line[perm] for perm in PERMS},
                },
                log,
            )
            kept |= access
        return kept

    def _apply_rules(self, log):
        """Create or update the ir.rule of each rule line; a domain on a
        model created by this Apply is checked now that it exists."""
        kept = self.env["ir.rule"].sudo()
        IrModel = self.env["ir.model"]
        for rule in self.rule_line_ids:
            self._studio_check_rule(rule)
            groups = rule.group_ids | rule.group_line_ids.mapped(
                lambda line: line._studio_group_record()
            )
            record, _differs = self._studio_save(
                "ir.rule",
                rule.xml_name,
                {
                    "name": rule.name,
                    "model_id": IrModel._get_id(rule.model),
                    "domain_force": rule.domain_force,
                    "groups": [(6, 0, groups.ids)],
                    **{perm: rule[perm] for perm in PERMS},
                },
                log,
            )
            kept |= record
        return kept

    def _studio_check_model_removal(self, models, keep=None):
        """Raise UserError when the custom models ``models`` cannot leave
        the database with the project: removing a model removes every field
        that points at it and the views of other projects on it, while
        another project, a module or a hand-made field still needs it.
        ``keep``: other records counted as the project's ({kind: records})."""
        self.ensure_one()
        if not models:
            return
        owned = models.filtered(lambda m: m.state != "manual")
        if owned:
            raise UserError(
                self.env._(
                    "Uninstall the module %(module)s first: it owns its models.",
                    module=self.module_name,
                )
            )
        keep = keep or {}
        names = models.mapped("model")
        Fields = self.env["ir.model.fields"].sudo()
        own_fields = self.field_ids | keep.get("fields", Fields)
        items = []
        pointing = Fields.search(
            [("relation", "in", names), ("model", "not in", names)]
        )
        # ``x_name`` and the fields of the options leave with the model.
        with_model = ["x_name"] + [o[0] for o in studio_arch.MODEL_OPTIONS.values()]
        on_models = Fields.search(
            [("model", "in", names), ("name", "not in", with_model)]
        )
        module_fields = set(
            self.env["ir.model.data"]
            .sudo()
            .search(
                [
                    ("model", "=", "ir.model.fields"),
                    ("res_id", "in", on_models.ids),
                    ("module", "!=", self.module_name),
                ]
            )
            .mapped("res_id")
        )
        for field in pointing | on_models:
            # A field on the models made by Odoo (the fields of the chatter)
            # goes with them; a custom field, or a field a module adds to
            # them or points at them with, belongs to someone else. A field
            # copied by « _inherits » (res.users from res.partner) is judged
            # by the field it copies.
            Model = self.env.get(field.model)
            definition = Model._fields.get(field.name) if Model is not None else None
            if definition is not None and definition.inherited:
                continue
            foreign = (
                field in pointing
                or field.state == "manual"
                or field.id in module_fields
            )
            if foreign and field not in own_fields:
                items.append(
                    self.env._("field %(field)s", field=f"{field.model}.{field.name}")
                )
        own_views = self.studio_view_ids | self.created_view_ids
        for kind in ("views", "primary_views"):
            own_views |= keep.get(kind, self.env["ir.ui.view"])
        for view in self.env["ir.ui.view"].sudo().search([("model", "in", names)]):
            if view not in own_views:
                items.append(self.env._("view %(view)s", view=view.name))
        items += self._studio_foreign_rights(models, keep)
        domain = [("project_id", "!=", self.id)]
        for model, label in (
            ("erplibre.studio.change", self.env._("change of the project %(project)s")),
            (
                "erplibre.studio.access",
                self.env._("access row of the project %(project)s"),
            ),
            ("erplibre.studio.rule", self.env._("rule of the project %(project)s")),
        ):
            for line in (
                self.env[model].sudo().search(domain + [("model", "in", names)])
            ):
                items.append(label % {"project": line.project_id.name})
        for change in (
            self.env["erplibre.studio.change"]
            .sudo()
            .search(domain + [("change_type", "=", "add_field")])
        ):
            if (change._payload().get("field") or {}).get("relation") in names:
                items.append(
                    self.env._(
                        "new field %(field)s of the project %(project)s",
                        field=f"{change.model}.{change.field_name}",
                        project=change.project_id.name,
                    )
                )
        if items:
            raise UserError(
                self.env._(
                    "The models %(models)s cannot be removed: %(items)s.",
                    models=", ".join(names),
                    items=", ".join(sorted(set(items))),
                )
            )

    def _studio_foreign_rights(self, models, keep):
        """The descriptions of the access rights and record rules on the
        custom models ``models`` that belong to someone else: created by
        another project, or under the external id of another module. The
        database deletes them with the model, which would leave their
        project or module with dangling external ids. A right made by hand,
        with no external id, goes with the model."""
        items = []
        Data = self.env["ir.model.data"].sudo()
        for res_model, field, kind, label in (
            (
                "ir.model.access",
                "created_access_ids",
                "access",
                self.env._("access right %(name)s"),
            ),
            (
                "ir.rule",
                "created_rule_ids",
                "rules",
                self.env._("record rule %(name)s"),
            ),
        ):
            Model = self.env[res_model].sudo().with_context(active_test=False)
            own = self[field] | keep.get(kind, Model)
            rows = Model.search([("model_id", "in", models.ids)]) - own
            if not rows:
                continue
            projects = self.sudo().search(
                [("id", "!=", self.id), (field, "in", rows.ids)]
            )
            modules = {
                data.res_id: data.module
                for data in Data.search(
                    [
                        ("model", "=", res_model),
                        ("res_id", "in", rows.ids),
                        ("module", "!=", self.module_name),
                    ]
                )
            }
            for row in rows:
                owner = next((p.name for p in projects if row in p[field]), None)
                owner = owner or modules.get(row.id)
                if owner:
                    items.append(label % {"name": f"{row.name} ({owner})"})
        return items

    @api.model
    def _studio_domain_fields(self, model, text):
        """The (model, field name) pairs the domain ``text`` of a rule on
        ``model`` names: every step of the path of each term, through the
        comodels of the relational fields, and the terms of the « any »
        sub-domains. A domain that does not evaluate names none."""
        try:
            domain = safe_eval(text or "[]", self.env["ir.rule"]._eval_context())
        except Exception:  # noqa: BLE001 - such a domain is refused elsewhere
            return set()
        found = set()

        def walk(model, domain):
            for term in domain if isinstance(domain, (list, tuple)) else []:
                if not (isinstance(term, (list, tuple)) and len(term) == 3):
                    continue
                path, operator, value = term
                if not isinstance(path, str):
                    continue
                current = model
                field = None
                for part in path.split("."):
                    found.add((current, part))
                    Model = self.env.get(current)
                    field = Model._fields.get(part) if Model is not None else None
                    if field is None or not field.relational:
                        break
                    current = field.comodel_name
                if operator in ("any", "not any") and field is not None:
                    walk(current, value)

        walk(model, domain)
        return found

    @api.model
    def _studio_change_name_text(self, change):
        """The text of ``change`` where a field name can appear: the field
        it adds or shows, its node path, and its payload without the texts
        people read (``HUMAN_ATTRIBUTES`` of its nodes, the label, tooltip
        and selection of a new field and the label of its inverse, the
        value of a relabel or a tooltip change). A label or a value that
        spells a field name does not name that field."""
        payload = change._payload()
        if change.change_type in ("relabel", "help"):
            payload.pop("value", None)
        field = payload.get("field")
        if isinstance(field, dict):
            for key in ("field_description", "help", "selection"):
                field.pop(key, None)
            for key in ("inverse_new", "inverse_o2m"):
                if isinstance(field.get(key), dict):
                    field[key].pop("field_description", None)
        node = payload.get("node")
        for attrs in (
            payload.get("node_attrs"),
            isinstance(node, dict) and node.get("attrs"),
        ):
            if isinstance(attrs, dict):
                for attr in HUMAN_ATTRIBUTES:
                    attrs.pop(attr, None)
        return " ".join(
            [
                change.field_name or "",
                change.xpath or "",
                json.dumps(payload, sort_keys=True),
            ]
        )

    @api.model
    def _studio_change_names(self, change, names):
        """The names of ``names`` (field names of the model of ``change``)
        that ``change`` names: as the field it adds or shows, in its node
        path, or in its parameters (a domain, an attribute value), its
        human texts aside (``_studio_change_name_text``)."""
        text = self._studio_change_name_text(change)
        return {
            name
            for name in names
            if re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text)
        }

    def _studio_check_field_removal(self, fields, removed_rules, own_changes):
        """Raise UserError while something still names one of ``fields``
        (ir.model.fields that leave the database): a record rule whose
        domain names it, which would make its model unreadable for the
        users it covers, or a change of a project that shows it, which
        could no longer apply. ``removed_rules`` leave with the fields;
        ``own_changes``: the changes of this project that stay in its
        views."""
        self.ensure_one()
        if not fields:
            return
        names = {}
        for field in fields:
            names.setdefault(field.model, set()).add(field.name)
        pairs = {(model, name) for model, items in names.items() for name in items}
        every = sorted({name for _model, name in pairs})
        items = []
        Rule = self.env["ir.rule"].sudo().with_context(active_test=False)
        domain = expression.OR([[("domain_force", "ilike", name)] for name in every])
        rules = Rule.search(domain) - removed_rules
        for rule in rules:
            named = self._studio_domain_fields(rule.model_id.model, rule.domain_force)
            if named & pairs:
                owner = (
                    self.sudo().search([("created_rule_ids", "in", rule.ids)], limit=1)
                ).name
                items.append(
                    self.env._(
                        "record rule %(name)s on %(model)s",
                        name=f"{rule.name} ({owner})" if owner else rule.name,
                        model=rule.model_id.model,
                    )
                )
        Change = self.env["erplibre.studio.change"].sudo()
        changes = own_changes | Change.search(
            [("project_id", "!=", self.id), ("model", "in", list(names))]
        )
        for change in changes:
            used = self._studio_change_names(change, names.get(change.model, ()))
            if used:
                items.append(
                    self.env._(
                        "change « %(change)s » of the view %(view)s (project "
                        "%(project)s)",
                        change=change.summary,
                        view=change._studio_view_label(),
                        project=change.project_id.name,
                    )
                )
        if items:
            raise UserError(
                self.env._(
                    "The fields %(fields)s cannot be removed, they are still "
                    "used: %(items)s.",
                    fields=", ".join(sorted(f"{m}.{n}" for m, n in pairs)),
                    items=", ".join(sorted(set(items))),
                )
            )

    def _studio_check_menu_removal(self, menus):
        """Raise UserError while a menu or a model line outside the project
        goes under one of ``menus``: Odoo would move it to the top level."""
        self.ensure_one()
        if not menus:
            return
        Menu = (
            self.env["ir.ui.menu"]
            .sudo()
            .with_context(**{"ir.ui.menu.full_list": True, "active_test": False})
        )
        others = Menu.search(
            [("parent_id", "in", menus.ids), ("id", "not in", menus.ids)]
        )
        lines = (
            self.env["erplibre.studio.model"]
            .sudo()
            .search(
                [("project_id", "!=", self.id), ("menu_parent_id", "in", menus.ids)]
            )
        )
        items = others.mapped("complete_name") + [
            self.env._("a model of the project %(project)s", project=p.name)
            for p in lines.project_id
        ]
        if items:
            raise UserError(
                self.env._(
                    "The menus %(menus)s cannot be removed: %(items)s go under them.",
                    menus=", ".join(menus.mapped("name")),
                    items=", ".join(items),
                )
            )

    def _studio_check_group_removal(self, groups, keep=None):
        """Raise UserError while something outside the project needs one of
        ``groups`` (res.groups the project created, that leave the
        database): a group that implies it, an access right, a rule, a menu,
        a view, an action or a field restricted to it, or a line of another
        project. Its users do not keep it: the confirmation lists them."""
        self.ensure_one()
        if not groups:
            return
        keep = keep or {}
        sudo = self.env["res.groups"].sudo().with_context(active_test=False)
        own_groups = groups | self.created_group_ids | keep.get("groups", sudo)
        items = [
            self.env._("group %(group)s", group=group.full_name)
            for group in sudo.search([("implied_ids", "in", groups.ids)]) - own_groups
        ]
        env = self.env(su=True, context=dict(self.env.context, active_test=False))

        def kept(kind, res_model):
            return keep.get(kind, self.env[res_model]).ids

        own = {
            "ir.model.access": self.created_access_ids.ids
            + kept("access", "ir.model.access"),
            "ir.rule": self.created_rule_ids.ids + kept("rules", "ir.rule"),
            "ir.ui.menu": self.created_menu_ids.ids + kept("menus", "ir.ui.menu"),
            "ir.ui.view": self.studio_view_ids.ids
            + self.created_view_ids.ids
            + kept("views", "ir.ui.view")
            + kept("primary_views", "ir.ui.view"),
            "ir.actions.act_window": self.created_action_ids.ids
            + kept("actions", "ir.actions.act_window"),
        }
        for res_model, field, label in (
            ("ir.model.access", "group_id", self.env._("access right %(name)s")),
            ("ir.rule", "groups", self.env._("record rule %(name)s")),
            ("ir.ui.menu", "groups_id", self.env._("menu %(name)s")),
            ("ir.ui.view", "groups_id", self.env._("view %(name)s")),
            ("ir.actions.act_window", "groups_id", self.env._("action %(name)s")),
            ("ir.actions.server", "groups_id", self.env._("action %(name)s")),
            ("ir.actions.report", "groups_id", self.env._("action %(name)s")),
            ("ir.model.fields", "groups", self.env._("field %(name)s")),
        ):
            Model = env.get(res_model)
            if Model is None:
                continue
            if res_model == "ir.ui.menu":
                Model = Model.with_context(**{"ir.ui.menu.full_list": True})
            rows = Model.search([(field, "in", groups.ids)])
            mine = set(own.get(res_model, ()))
            rows = rows.filtered(lambda r, m=mine: r.id not in m)
            items += [label % {"name": row.display_name} for row in rows]
        domain = [("project_id", "!=", self.id)]
        for model, field, label in (
            (
                "erplibre.studio.access",
                "group_id",
                self.env._("access row of the project %(project)s"),
            ),
            (
                "erplibre.studio.rule",
                "group_ids",
                self.env._("rule of the project %(project)s"),
            ),
            (
                "erplibre.studio.group",
                "implied_group_ids",
                self.env._("group of the project %(project)s"),
            ),
        ):
            for line in env[model].search(domain + [(field, "in", groups.ids)]):
                items.append(label % {"project": line.project_id.name})
        if items:
            raise UserError(
                self.env._(
                    "The groups %(groups)s cannot be removed: %(items)s still "
                    "need them.",
                    groups=", ".join(groups.mapped("full_name")),
                    items=", ".join(sorted(set(items))),
                )
            )

    def _studio_check_category_removal(self, categories, keep=None):
        """Raise UserError while a group the project did not create is in one
        of ``categories``."""
        self.ensure_one()
        if not categories:
            return
        keep = keep or {}
        Groups = self.env["res.groups"].sudo().with_context(active_test=False)
        own = self.created_group_ids | keep.get("groups", Groups)
        others = Groups.search([("category_id", "in", categories.ids)]) - own
        if others:
            raise UserError(
                self.env._(
                    "The categories %(categories)s cannot be removed: the groups "
                    "%(groups)s are in them.",
                    categories=", ".join(categories.mapped("name")),
                    groups=", ".join(others.mapped("full_name")),
                )
            )

    @api.model
    def _studio_cascade_records(self, models, fields=None):
        """[records] the database deletes in cascade with the ir.model
        ``models`` and the ir.model.fields ``fields`` (the fields of
        ``models`` included): the records of a stored many2one to ir.model
        or ir.model.fields with « ondelete cascade », in a model that is
        neither transient nor in CASCADE_SKIPPED (server and scheduled
        actions, actions bound to the models, e-mail templates, automation
        rules, default values...); then the ir.filters of ``models``, which
        name their model by its name and would stay behind. The default
        values for everyone of the fields of the options of the models the
        studio creates (``_apply_model_options``), removed with ``models``
        or among ``fields``, are the studio's own: left out, and so are the
        layers the project wrote (``_studio_geo_layer_records``), removed
        before the fields they draw. A read, in sudo."""
        Fields = self.env["ir.model.fields"].sudo()
        own_layers = {
            records._name: records
            for records in self._studio_geo_layer_records().values()
        }
        fields = (fields or Fields) | Fields.search([("model_id", "in", models.ids)])
        targets = {"ir.model": models.ids, "ir.model.fields": fields.ids}
        options = [option[0] for option in studio_arch.MODEL_OPTIONS.values()]
        studio_models = set(
            self.env["erplibre.studio.model"]
            .sudo()
            .search([("model", "in", fields.mapped("model"))])
            .mapped("model")
        )

        def own_default(row):
            return (
                row.field_id.name in options
                and (
                    row.field_id.model_id in models
                    or row.field_id.model in studio_models
                )
                and not (row.user_id or row.company_id or row.condition)
            )

        found = []
        for name in sorted(self.env.registry):
            Model = self.env[name]
            if (
                Model._abstract
                or Model._transient
                or name in CASCADE_SKIPPED
                or name.startswith("erplibre.studio.")
            ):
                continue
            for field in Model._fields.values():
                ids = (
                    targets.get(field.comodel_name)
                    if field.type == "many2one"
                    else None
                )
                if not ids or not field.store or field.ondelete != "cascade":
                    continue
                rows = (
                    Model.sudo()
                    .with_context(active_test=False)
                    .search([(field.name, "in", ids)])
                )
                if name == "ir.default":
                    rows = rows.filtered(lambda row: not own_default(row))
                rows -= own_layers.get(name, rows.browse())
                if rows:
                    found.append(rows)
        if models:
            filters = (
                self.env["ir.filters"]
                .sudo()
                .with_context(active_test=False)
                .search([("model_id", "in", models.mapped("model"))])
            )
            if filters:
                found.append(filters)
        return found

    @api.model
    def _studio_record_label(self, record):
        """« <kind of record> <its name> », to name ``record`` to the
        user."""
        kind = self.env["ir.model"]._get(record._name).name or record._name
        return f"{kind} {record.display_name}"

    def _studio_check_cascade(self, models, fields):
        """Raise UserError while records outside the project would leave the
        database in cascade with the ir.model ``models`` or the ir.model.fields
        ``fields`` (``_studio_cascade_records``, but for the filters, which
        the removal deletes with their model): made by hand, they belong to
        no project and nothing would recreate them."""
        self.ensure_one()
        if not (models or fields):
            return
        items = [
            self._studio_record_label(record)
            for rows in self._studio_cascade_records(models, fields)
            if rows._name != "ir.filters"
            for record in rows
        ]
        if items:
            raise UserError(
                self.env._(
                    "These records would be deleted with what the project "
                    "removes: %(items)s. Delete them first, or move them to "
                    "another model.",
                    items=", ".join(sorted(set(items))),
                )
            )

    def _studio_check_removal(self, records, keep=None, own_changes=None):
        """Raise UserError while ``records`` ({kind: records}, kinds of
        REMOVAL_ORDER) cannot leave the database: what they would take with
        them belongs to someone else, or still names them. ``keep``: see
        ``_studio_check_model_removal``; ``own_changes``: see
        ``_studio_remove_created``."""
        self.ensure_one()
        records = {kind: value.exists() for kind, value in records.items() if value}
        models = records.get("models", self.env["ir.model"])
        self._studio_check_model_removal(models, keep)
        self._studio_check_menu_removal(records.get("menus", self.env["ir.ui.menu"]))
        self._studio_check_group_removal(
            records.get("groups", self.env["res.groups"]), keep
        )
        self._studio_check_category_removal(
            records.get("categories", self.env["ir.module.category"]), keep
        )
        # The fields that leave: the custom fields of the project, and with
        # a model, its fields and those pointing at it. The rules on a
        # removed model go with it.
        leaving = self._studio_leaving_fields(records)
        removed_rules = records.get("rules", self.env["ir.rule"])
        if models:
            removed_rules |= (
                self.env["ir.rule"]
                .sudo()
                .with_context(active_test=False)
                .search([("model_id", "in", models.ids)])
            )
        self._studio_check_field_removal(
            leaving,
            removed_rules,
            own_changes or self.env["erplibre.studio.change"],
        )
        self._studio_check_cascade(models, leaving)

    @api.model
    def _studio_drop_model_leftovers(self, model_names):
        """Delete what the removal of the models ``model_names`` leaves in the
        database: their ir.filters, and the external ids Odoo gives the
        inheritance of a custom model (« False.model_inherit__<model>__... »,
        a model with a chatter), whose ir.model.inherit went with it."""
        if not model_names:
            return
        self.env["ir.filters"].sudo().with_context(active_test=False).search(
            [("model_id", "in", list(model_names))]
        ).unlink()
        prefixes = tuple(
            f"model_inherit__{name.replace('.', '_')}__" for name in model_names
        )
        Data = self.env["ir.model.data"].sudo()
        data = Data.search(
            [("module", "=", "False"), ("model", "=", "ir.model.inherit")]
        ).filtered(lambda d: d.name.startswith(prefixes))
        gone = data.filtered(
            lambda d: not self.env["ir.model.inherit"].sudo().browse(d.res_id).exists()
        )
        gone.unlink()

    def _studio_remove_created(self, records, log, keep=None, own_changes=None):
        """Remove ``records`` ({kind: records}, kinds of REMOVAL_ORDER) from
        the database with their external ids, in that order; a field goes
        only while custom. The changes of the project on a removed default
        view go with it, and so do the filters of a removed model. ``keep``:
        see ``_studio_check_model_removal``; ``own_changes``: the changes of
        the project that stay in its views, which may not name a removed
        field. Return the number of the changes removed with the default
        views."""
        self.ensure_one()
        Data = self.env["ir.model.data"].sudo()
        records = {kind: value.exists() for kind, value in records.items() if value}
        self._studio_check_removal(records, keep, own_changes)
        model_names = records.get("models", self.env["ir.model"]).mapped("model")
        removed_changes = 0
        for kind in REMOVAL_ORDER:
            value = records.get(kind)
            if kind == "fields" and value:
                value = value.filtered(lambda f: f.state == "manual")
            if not value:
                continue
            value = value.exists()
            if kind == "primary_views":
                self._studio_unbind_added_changes(value)
                changes = self.change_ids.filtered(lambda c: c.view_id in value)
                removed_changes = len(changes)
                changes.with_context(**{NO_TOUCH_KEY: True}).unlink()
            Data.search(
                [("model", "=", value._name), ("res_id", "in", value.ids)]
            ).unlink()
            # The project created them in sudo: the categories of groups,
            # for one, no group may delete.
            value = value.sudo()
            if kind == "fields":
                # A many2one that is the inverse of a custom one2many goes
                # only once the one2many is gone, in an unlink of its own.
                one2many = value.filtered(lambda f: f.ttype == "one2many")
                one2many.unlink()
                (value - one2many).exists().unlink()
            else:
                value.unlink()
            log.append(f"{len(value)} {kind} removed")
        self._studio_drop_model_leftovers(model_names)
        return removed_changes

    def action_apply(self, digest=None):
        """Write the draft into the database: the categories and groups, the
        models, the new fields, the default views of the models (the
        changes recorded on them before they existed bound to them), one
        inherited view per edited view, the actions, the menus, the access
        rights and the rules; then remove what the draft no longer has.
        Applying again updates them. When Apply removes records, values or
        group members, ``digest`` must be the one of the report the user
        confirmed (``_studio_apply_report``); server code in sudo is not
        asked. Return True, or a warning notification that names what waits
        for the next generation of the installed module."""
        self._check_studio_access()
        waiting = []
        for project in self:
            log = []
            project._studio_check_apply()
            project._studio_check_digest("apply", digest)
            before = {kind: project[name] for kind, name in CREATED_FIELDS.items()}
            before["views"] = project.studio_view_ids
            before["fields"] = project.field_ids
            before.update(project._studio_geo_layer_records())
            # The fields of the options turned off are not fields of the
            # project: they leave on their own, after everything that names
            # them was rewritten without them.
            option_fields, waiting_options = project._studio_option_removals()
            kept = {}
            kept["categories"] = project._apply_categories(log)
            kept["groups"] = project._apply_groups(log)
            kept["models"], waiting_models = project._apply_models(log)
            owned = set(
                kept["models"].filtered(lambda m: m.state != "manual").mapped("model")
            )
            kept["fields"], waiting_fields = project._apply_fields(log)
            waiting_models += project._apply_model_options(log, owned)
            kept["primary_views"], waiting_views = project._apply_model_views(
                log, owned
            )
            kept["primary_views"] |= project._apply_added_views(log)
            kept.update(project._apply_geo_layers(log))
            project.new_model_ids.invalidate_recordset(["applied", "ir_model_id"])
            project._studio_bind_pending_changes()
            kept["views"] = project._apply_views(log)
            kept["actions"] = project._apply_actions(log)
            kept["menus"], waiting_icons = project._apply_menus(log)
            kept["access"] = project._apply_access(log)
            kept["rules"] = project._apply_rules(log)
            waiting += waiting_models + waiting_fields + waiting_views + waiting_icons
            waiting += waiting_options
            removed = {kind: before[kind] - kept[kind] for kind in before}
            removed["fields"] |= option_fields
            project._studio_remove_created(
                removed,
                log,
                kept,
                own_changes=project.change_ids,
            )
            vals = {
                name: [(6, 0, kept[kind].exists().ids)]
                for kind, name in CREATED_FIELDS.items()
            }
            vals.update(
                {
                    "field_ids": [(6, 0, kept["fields"].exists().ids)],
                    "studio_view_ids": [(6, 0, kept["views"].exists().ids)],
                    "applied_snapshot": project._current_snapshot(),
                    "applied_date": fields.Datetime.now(),
                    # Apply created the models the approval was for: a model
                    # line put back as a draft (Revert) needs a new one.
                    **APPROVAL_CLEARED,
                }
            )
            project._internal().write(vals)
            project.new_model_ids.invalidate_recordset(["applied", "ir_model_id"])
            project.view_line_ids.invalidate_recordset(["applied", "view_id"])
            project._touch()
            _logger.info("Studio project %s applied: %s", project.module_name, log)
        if not waiting:
            return True
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "warning",
                "sticky": True,
                "title": self.env._("Applied"),
                "message": self.env._(
                    "The installed generated module defines these fields, "
                    "models or views: their new definition takes effect once "
                    "the module is regenerated and upgraded: %(fields)s",
                    fields=", ".join(waiting),
                ),
                "next": {"type": "ir.actions.client", "tag": "soft_reload"},
            },
        }

    def action_revert(self, digest=None):
        """Remove from the database what the project created: its menus,
        actions, rules, access rights, views, custom fields and models, with
        the records of these models, its groups and their categories. The
        lines and the changes stay, as a draft, but for the changes of the
        default views of its models, which go with the views. Refused while
        the generated module is installed or owns a model
        (``_studio_revert_refusal``), even when the call skips the
        confirmation. ``digest`` must be the one of the
        report the user confirmed (``_studio_revert_report``); server code
        in sudo is not asked. Return True, or a notification that counts
        the changes removed with the default views."""
        self._check_studio_access()
        removed = 0
        for project in self:
            log = []
            refusal = project._studio_revert_refusal(checks=False)
            if refusal:
                raise UserError(refusal)
            project._studio_check_digest("revert", digest)
            records = {kind: project[name] for kind, name in CREATED_FIELDS.items()}
            records["views"] = project.studio_view_ids
            records["fields"] = project.field_ids
            records.update(project._studio_geo_layer_records())
            removed += project._studio_remove_created(records, log)
            vals = {name: [(5, 0, 0)] for name in CREATED_FIELDS.values()}
            vals.update(
                {
                    "field_ids": [(5, 0, 0)],
                    "studio_view_ids": [(5, 0, 0)],
                    "applied_snapshot": False,
                    "applied_date": False,
                    **APPROVAL_CLEARED,
                }
            )
            project._internal().write(vals)
            project.new_model_ids.invalidate_recordset(["applied", "ir_model_id"])
            project.view_line_ids.invalidate_recordset(["applied", "view_id"])
            project._touch()
            _logger.info("Studio project %s reverted: %s", project.module_name, log)
        if not removed:
            return True
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "warning",
                "sticky": True,
                "title": self.env._("Reverted"),
                "message": self.env._(
                    "%(count)s change(s) of the default views of the new "
                    "models were removed with these views.",
                    count=removed,
                ),
                "next": {"type": "ir.actions.client", "tag": "soft_reload"},
            },
        }

    def _studio_uninstall_reset_vals(self):
        """The values of the project once its generated module is
        uninstalled: nothing in the database, no Apply, no approval."""
        vals = {name: [(5, 0, 0)] for name in CREATED_FIELDS.values()}
        vals.update(
            {
                "field_ids": [(5, 0, 0)],
                "studio_view_ids": [(5, 0, 0)],
                "applied_snapshot": False,
                "applied_date": False,
                **APPROVAL_CLEARED,
                "state": "draft",
            }
        )
        return vals

    def _studio_reset_after_uninstall(self):
        """Back to a draft with its lines, once the generated module left the
        database with what the project applied; the changes of the default
        views of its models went with these views."""
        for project in self:
            project._internal().write(project._studio_uninstall_reset_vals())
            project.new_model_ids.invalidate_recordset(["applied", "ir_model_id"])
            project.view_line_ids.invalidate_recordset(["applied", "view_id"])
            project._touch()

    def action_open_editor(self):
        """The editor on the first view the project changes, else on the
        form of its first model, else on the first view it adds."""
        self.ensure_one()
        view = self.change_ids.filtered("view_id")[:1].view_id
        if not view:
            applied = self.new_model_ids.filtered("applied")[:1]
            view = applied and applied._studio_views().get("form")
        Editor = self.env["erplibre.studio.editor"]
        added = self.view_line_ids[:1]
        if not view and not self.new_model_ids and added:
            return Editor.action_customize(
                added.model, added.view_id.id, added.view_type, project_id=self.id
            )
        if not view:
            line = self.new_model_ids[:1]
            if not line:
                raise UserError(
                    self.env._("Open the editor from the debug menu of a view.")
                )
            return Editor.action_customize(
                line.model, False, "form", project_id=self.id
            )
        return Editor.action_customize(
            view.model, view.id, view.type, project_id=self.id
        )


def normal_arch(text):
    """``text``, an arch, without the blank text between its nodes, to
    compare two archs."""
    if not text:
        return ""
    parser = etree.XMLParser(remove_blank_text=True)
    return etree.tostring(etree.fromstring(text, parser))


def etree_placeholder(label, note):
    """The form element that stands for a field not yet created."""
    div = etree.Element(
        "div",
        {"class": "alert alert-info py-1 px-2 mb-1 o_erplibre_studio_pending"},
    )
    strong = etree.SubElement(div, "strong")
    strong.text = label
    span = etree.SubElement(div, "span", {"class": "text-muted ms-1"})
    span.text = f"({note})"
    return div


def remove_keeping_tail(node):
    """Remove ``node`` from its parent; the text that follows it stays."""
    parent = node.getparent()
    if node.tail:
        previous = node.getprevious()
        if previous is not None:
            previous.tail = (previous.tail or "") + node.tail
        else:
            parent.text = (parent.text or "") + node.tail
    parent.remove(node)


def check_domain_shape(domain):
    """Raise ValueError unless ``domain`` is a list of terms (field,
    operator, value) and of « & », « | », « ! » that combine them."""
    for token in domain:
        if not (expression.is_operator(token) or expression.is_leaf(token)):
            raise ValueError(f"invalid term {token!r}")
    expression.normalize_domain(list(domain))
