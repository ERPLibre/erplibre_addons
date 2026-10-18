# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

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
from odoo.tools.misc import file_path
from odoo.tools.safe_eval import safe_eval

from .. import arch as studio_arch
from .studio_pending import is_pending_view, pending_view

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
REMOVAL_ORDER = (
    "menus",
    "actions",
    "rules",
    "access",
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
# What a many2one does when its record is deleted.
ON_DELETE = ("set null", "cascade", "restrict")

# The editor operations on a view of a model not created yet: those that
# need no record nor field of the database (no filter, no group-by).
PENDING_VIEW_OPERATIONS = {
    "form": (
        "add_field",
        "add_existing_field",
        "move",
        "remove",
        "hide",
        "relabel",
        "required",
        "readonly",
        "help",
        "update_field",
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
    ),
    "search": ("add_existing_field", "move", "remove"),
}

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
    pivot, timeline) that make one module. Its life: draft changes (previewed by its editor only), then
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
        yet, only their shape. Raise UserError, naming the rule ``name``,
        when it does not apply."""
        try:
            if len(text or "") > RULE_DOMAIN_SIZE:
                raise ValueError(
                    self.env._("longer than %(size)s characters", size=RULE_DOMAIN_SIZE)
                )
            domain = safe_eval(text or "[]", self.env["ir.rule"]._eval_context())
            if not isinstance(domain, (list, tuple)):
                raise ValueError(self.env._("a domain is a list"))
            if model in self.env:
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

    # ── state ───────────────────────────────────────────────────────────

    def _current_snapshot(self):
        """The JSON of the draft, to compare it with the one applied. A
        project with changes of views only keeps the form of a list of its
        changes, the one of the projects recorded before the models."""
        self.ensure_one()
        changes = self.change_ids._snapshot()
        lines = (
            self.new_model_ids
            or self.access_line_ids
            or self.rule_line_ids
            or self.app_ids
            or self.group_line_ids
        )
        if not lines:
            return json.dumps(changes, sort_keys=True)
        return json.dumps(
            {
                "changes": changes,
                "models": self.new_model_ids._snapshot(),
                "access": self.access_line_ids._snapshot(),
                "rules": self.rule_line_ids._snapshot(),
                "apps": self.app_ids._snapshot(),
                "groups": self.group_line_ids._snapshot(),
            },
            sort_keys=True,
        )

    @api.model
    def _studio_load_snapshot(self, text):
        """The dict {changes, models, access, rules, apps, groups} of the
        snapshot ``text``, whichever form ``_current_snapshot`` gave it. A
        snapshot with a single « app » {name, icon, sequence} gives the app
        « menu_app », where its models « in the app » go; its rules without
        a group on a model it creates are global."""
        value = json.loads(text or "[]")
        if isinstance(value, list):
            value = {"changes": value}
        snapshot = {
            key: value.get(key) or []
            for key in ("changes", "models", "access", "rules", "apps", "groups")
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
        """The changes of ``view``, a view or a pending view (see
        ``StudioPendingView``), in the order they apply."""
        self.ensure_one()
        if is_pending_view(view):
            changes = self.change_ids.filtered(
                lambda c: c.model_line_id == view.line and c.view_type == view.type
            )
        else:
            changes = self.change_ids.filtered(lambda c: c.view_id == view)
        return changes.sorted(lambda c: (c.sequence, c.id))

    def _change_view(self, change):
        """The view ``change`` is on: its view, or the pending view of its
        model line."""
        if change.view_id:
            return change.view_id
        return pending_view(change.model_line_id, change.view_type)

    def _base_arch(self, view, branding=False):
        """The combined arch of ``view`` without the views of the project;
        of a pending view, the default arch of its model line."""
        self.ensure_one()
        if is_pending_view(view):
            return etree.fromstring(self._studio_default_arch(view.line, view.type))
        context = {EXCLUDE_KEY: ViewExclusion(self.studio_view_ids.ids)}
        if branding:
            context["inherit_branding"] = True
        View = self.env["ir.ui.view"].sudo().with_context(**context)
        return View.browse(view.id)._get_combined_arch()

    def _draft_arch(self, view):
        """(arch, errors): the base arch of ``view`` with the changes of the
        project applied; ``errors`` maps a change id to why it does not
        apply."""
        self.ensure_one()
        return self._draft_arch_without(view, self.env["erplibre.studio.change"])

    def _draft_arch_without(self, view, skipped):
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
        types."""
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
        model (simulated for a model not created yet), those the projects
        add to it, and the inverse many2one their one2many create on it."""
        line = self._studio_pending_line(model)
        if line:
            names = set(self._studio_simulated_fields(line))
        else:
            names = set(self.env[model]._fields)
        Change = self.env["erplibre.studio.change"]
        names |= set(
            Change.search(
                [("model", "=", model), ("change_type", "=", "add_field")]
            ).mapped("field_name")
        )
        for change in Change.search(
            [("change_type", "=", "add_field"), ("payload", "ilike", "inverse_new")]
        ):
            field = change._payload().get("field") or {}
            inverse = field.get("inverse_new") or {}
            if field.get("relation") == model and inverse.get("name"):
                names.add(inverse["name"])
        return names

    def _clean_field_definition(self, model, field, name=None, existing=None):
        """A checked definition of a new field: {ttype, field_description,
        readonly, help, selection, relation, on_delete, relation_field,
        inverse_new, relation_table, column1, column2, currency_field}.
        ``name`` is the field name; None makes one from the label.
        ``existing``: the definition the field had, whose relation an x2many
        keeps."""
        ttype = field.get("ttype")
        if ttype not in NEW_FIELD_TYPES:
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
        if ttype == "selection":
            definition["selection"] = self._clean_selection(field)
        elif ttype == "many2one":
            definition["relation"] = self._clean_relation(field)
            definition["on_delete"] = self._clean_on_delete(field)
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
    def _check_field_texts(self, label, help_text):
        """Raise UserError when the label or the tooltip of a new field
        cannot be recorded. Every text is accepted here; a module that
        copies them elsewhere narrows the check."""

    def _clean_field_name(self, model, label, field, name):
        if name is None:
            taken = self._taken_field_names(model)
            name = field.get("name") or studio_arch.field_name_from_label(label, taken)
            if name in taken:
                raise UserError(
                    self.env._("The field %(name)s already exists.", name=name)
                )
        if not studio_arch.valid_field_name(name):
            raise UserError(
                self.env._(
                    "%(name)s is not a valid field name: x_ then lower case "
                    "letters, digits and underscores.",
                    name=name,
                )
            )
        return name

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
            "x2many_view": lambda: self.env._("A one2many shows in a form only."),
            "many2many_view": lambda: self.env._(
                "A many2many shows in a form, a list or a kanban only."
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
            "add_widget": self._op_add_widget,
            "move": self._op_move,
            "update_field": lambda view, arch, op: self._update_field(view, op),
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

    def _check_pivot_axis(self, model, name, axis, interval=None):
        """The pivot attributes {type, interval} of the field ``name`` on
        ``axis``: a measure adds up a number, a row or a column groups."""
        if axis not in studio_arch.PIVOT_AXES:
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
        sub-list in a form, a many2many as tags in a list or a kanban."""
        target, position, _node = self._check_drop(arch, op, view.type)
        field = op.get("field") or {}
        self._refuse(studio_arch.x2many_refusal(view.type, field.get("ttype")))
        name, definition = self._clean_field_definition(view.model, field)
        payload = {"field_name": name, "field": definition, "node_attrs": {}}
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
        node_attrs = {}
        extra = {}
        if view.type == "timeline" and studio_arch.in_template(node):
            extra = self._item_field(view.model, arch, name)
        elif view.type == "search":
            if not self._field_info(view.model, name).get("searchable"):
                raise UserError(
                    self.env._("The records cannot be searched by %(name)s.", name=name)
                )
        elif view.type == "pivot":
            node_attrs = self._check_pivot_axis(
                view.model, name, op.get("axis"), op.get("interval")
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
        target, position, _node = self._check_drop(arch, op, view.type)
        return self._add_change(
            view,
            "add_node",
            target,
            position,
            {"kind": "separator", "node": {"tag": "separator", "attrs": {}}},
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
        """Move a node; in a pivot, ``axis`` also moves a field to another
        axis."""
        target, position, node = self._check_drop(arch, op, view.type)
        source_path = op.get("source")
        source = self._locate(arch, source_path)
        self._refuse(studio_arch.move_refusal(view.type, source))
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
        if view.type == "pivot" and source.tag == "field" and axis:
            if axis != source.get("type"):
                interval = None if axis == "measure" else source.get("interval")
                attrs = self._check_pivot_axis(
                    view.model, source.get("name"), axis, interval
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
        return self._add_change(view, "move", target, position, payload)

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
        if kind == "colors":
            return self._colors_value(view.model, value)
        if value in (None, "", False):
            return "", []
        if not isinstance(value, str):
            raise UserError(self.env._("Invalid value %(value)s.", value=value))
        check = {
            "group_field": self._group_field_value,
            "relation_group_field": self._relation_group_field_value,
            "date_field": self._typed_field_value,
            "number_field": self._typed_field_value,
            "order": self._order_value,
            "axis": self._axis_value,
            "interval": self._interval_value,
            "widget": lambda model, node, kind, value: (self._clean_widget(value), []),
            "timeline_mode": self._mode_value,
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
        interval = node.get("interval")
        if value == "measure" and interval:
            raise UserError(
                self.env._("A measure takes no interval: remove the interval first.")
            )
        self._check_pivot_axis(model, node.get("name"), value, interval)
        return value, []

    def _interval_value(self, model, node, kind, value):
        if node.get("type") == "measure":
            raise UserError(self.env._("A measure takes no interval."))
        info = self._field_info(model, node.get("name"))
        return self._check_interval(info, value), []

    def _mode_value(self, model, node, kind, value):
        if value not in studio_arch.TIMELINE_MODES:
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
        if kind == "bool":
            if studio_arch.constant_true(text):
                return "True"
            if text in ("0", "False", "false"):
                return "False"
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
        if not kind:
            raise UserError(
                self.env._(
                    "The attribute %(attribute)s of <%(tag)s> cannot be set here.",
                    attribute=attribute,
                    tag=node.tag,
                )
            )
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
        if replaced:
            before, _errors = self._draft_arch_without(view, replaced)
            original = self._locate(before, xpath).get(attribute)
        else:
            original = node.get(attribute)
        if value == self._normal_attribute(kind, original):
            replaced.unlink()
            return replaced.browse()
        payload = {"attribute": attribute, "value": value, "fields": named}
        if replaced:
            replaced._set_payload(payload)
            return replaced
        return self._add_change(view, "set_attribute", xpath, "attributes", payload)

    def _update_field(self, view, op):
        name = op.get("field_name")
        change = self._field_add_change(view.model, name)
        if not change:
            raise UserError(
                self.env._("%(name)s is not a field of this project.", name=name)
            )
        payload = change._payload()
        definition = dict(payload.get("field") or {}, **(op.get("field") or {}))
        if definition.get("ttype") != payload["field"].get("ttype"):
            raise UserError(self.env._("The type of a field cannot change."))
        _name, definition = self._clean_field_definition(
            view.model, definition, name=name, existing=payload["field"]
        )
        payload["field"] = definition
        change._set_payload(payload)
        return change

    def _remove_node(self, view, arch, op):
        """Remove a node: one the project added leaves the project with the
        changes that name it; any other node is hidden, or removed from
        the arch in a view type whose hide mode is « remove »."""
        xpath = op.get("target")
        node = self._locate(arch, xpath)
        if node.getparent() is None:
            raise UserError(self.env._("The view itself cannot be removed."))
        added = self._added_changes(view, xpath)
        if added:
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
        """Raise UserError when another model line (than ``line``) of any
        project creates ``model``."""
        other = (
            self.env["erplibre.studio.model"]
            .sudo()
            .search([("model", "=", model), ("id", "!=", line.id if line else 0)])
        )
        if other:
            raise UserError(
                self.env._(
                    "The project %(project)s creates the model %(name)s already.",
                    project=other.project_id.name,
                    name=model,
                )
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
        ``_studio_menu_vals``}, with the default access row (the internal
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
        """Write ``values`` {name, model, chatter, menu, sequence} on the
        model line ``line`` (see ``erplibre.studio.model.write``)."""
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
            self._studio_check_free_model(vals["model"], line)
        line.write(vals)
        self._touch()
        return line

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
        project.access_line_ids.filtered(lambda a: a.group_line_id == group).unlink()
        group.with_context(**{NO_TOUCH_KEY: True}).unlink()
        self._touch()

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
            view_type, (line.name or "").strip(), line.chatter
        )

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
        so that the next Apply finds it."""
        self.ensure_one()
        old_name = self.module_name
        Data = self.env["ir.model.data"].sudo()
        records = [self.studio_view_ids, self.field_ids] + [
            self[name] for name in CREATED_FIELDS.values()
        ]
        for record in records:
            if record:
                Data.search(
                    [
                        ("module", "=", old_name),
                        ("model", "=", record._name),
                        ("res_id", "in", record.ids),
                    ]
                ).write({"module": new_name})
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
        vals = {
            "field_description": definition["field_description"],
            "readonly": definition.get("readonly", False),
            "help": definition.get("help") or False,
        }
        ttype = definition["ttype"]
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
        return vals

    def _apply_fields(self, log):
        """Create or update the ``x_`` fields of the project, in the order of
        ``_studio_all_definitions``. Return (fields kept, names of the fields
        whose new definition waits for the module): a field the generated
        module defines, once installed, changes with the module only."""
        Fields = self.env["ir.model.fields"].sudo()
        kept = Fields
        waiting = []
        for model, name, definition, _change in self._studio_all_definitions():
            vals = self._field_vals(model, name, definition)
            field = Fields._get(model, name)
            if not field:
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
        with the module that defines them."""
        self.ensure_one()
        mail = self._studio_mail_available()
        for line in self.new_model_ids:
            self._studio_check_menu(line)
            if line.chatter and not mail:
                raise UserError(
                    self.env._("A chatter needs the module mail (Discuss).")
                )
            if line.model in self.env and not line.applied:
                raise UserError(
                    self.env._("The model %(name)s already exists.", name=line.model)
                )
            if line.model not in self.access_line_ids.mapped("model"):
                # Without one, the model is the superuser's only, and the
                # generated module has no access file.
                raise UserError(
                    self.env._(
                        "The model %(name)s needs at least one access right.",
                        name=line.model,
                    )
                )
        for line in self.access_line_ids:
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
        self._studio_check_apply_rules()
        self._studio_check_apply_groups()
        for change in self.change_ids:
            if not change.view_id and change.model_line_id.project_id != self:
                raise UserError(
                    self.env._(
                        "The change « %(change)s » is on no view of the project.",
                        change=change.summary,
                    )
                )
        self._studio_check_relations()
        names = self._studio_new_models()
        self._studio_check_model_removal(
            self.created_model_ids.exists().filtered(lambda m: m.model not in names)
        )

    def _studio_check_apply_rules(self):
        """The checks of the rule lines before Apply: the groups they name,
        a group or « Global », and their domain on an existing model."""
        self.ensure_one()
        for rule in self.rule_line_ids:
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

    def _apply_models(self, log):
        """Create or update the custom models of the model lines, with their
        ``x_name``. Return (models kept, names of the models whose new label
        or chatter waits for the module): a model the generated module
        defines, once installed, changes with the module only."""
        IrModel = self.env["ir.model"].sudo().with_context(lang=None)
        kept = IrModel
        waiting = []
        mail = self._studio_mail_available()
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
                record = IrModel.create(vals)
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
                kept |= view
        return kept, waiting

    def _apply_actions(self, log):
        """Create or update the window action of each model line."""
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
                    "view_mode": "list,form",
                    "search_view_id": search.id,
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
        before Apply created them, to these views, now created: their node
        paths were recorded on the default arch."""
        self.ensure_one()
        for change in self.change_ids.filtered("model_line_id"):
            view = change.model_line_id._studio_views().get(change.view_type)
            if view:
                change.with_context(**{NO_TOUCH_KEY: True}).sudo().write(
                    {"view_id": view.id, "model_line_id": False}
                )

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
        on_models = Fields.search([("model", "in", names), ("name", "!=", "x_name")])
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
    def _studio_change_names(self, change, names):
        """The names of ``names`` (field names of the model of ``change``)
        that ``change`` names: as the field it adds or shows, in its node
        path, or in its parameters (a domain, an attribute value)."""
        text = " ".join(
            [change.field_name or "", change.xpath or "", change.payload or ""]
        )
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
        name their model by its name and would stay behind. A read, in
        sudo."""
        Fields = self.env["ir.model.fields"].sudo()
        fields = (fields or Fields) | Fields.search([("model_id", "in", models.ids)])
        targets = {"ir.model": models.ids, "ir.model.fields": fields.ids}
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
            kept = {}
            kept["categories"] = project._apply_categories(log)
            kept["groups"] = project._apply_groups(log)
            kept["models"], waiting_models = project._apply_models(log)
            owned = set(
                kept["models"].filtered(lambda m: m.state != "manual").mapped("model")
            )
            kept["fields"], waiting_fields = project._apply_fields(log)
            kept["primary_views"], waiting_views = project._apply_model_views(
                log, owned
            )
            project.new_model_ids.invalidate_recordset(["applied", "ir_model_id"])
            project._studio_bind_pending_changes()
            kept["views"] = project._apply_views(log)
            kept["actions"] = project._apply_actions(log)
            kept["menus"], waiting_icons = project._apply_menus(log)
            kept["access"] = project._apply_access(log)
            kept["rules"] = project._apply_rules(log)
            waiting += waiting_models + waiting_fields + waiting_views + waiting_icons
            project._studio_remove_created(
                {kind: before[kind] - kept[kind] for kind in before},
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
            project._touch()

    def action_open_editor(self):
        """The editor on the first view the project changes, else on the
        form of its first model."""
        self.ensure_one()
        view = self.change_ids.filtered("view_id")[:1].view_id
        if not view:
            applied = self.new_model_ids.filtered("applied")[:1]
            view = applied and applied._studio_views().get("form")
        Editor = self.env["erplibre.studio.editor"]
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
