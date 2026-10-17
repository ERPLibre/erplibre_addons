# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import base64
import hashlib
import logging
import os
import shutil
import time
from contextlib import contextmanager

import odoo
from odoo import api, fields, models, release
from odoo.addons.erplibre_info import runner
from odoo.addons.erplibre_studio import arch as studio_arch
from odoo.addons.erplibre_studio.models.erplibre_studio_project import (
    PERMS as studio_perms,
)
from odoo.exceptions import UserError, ValidationError
from odoo.tools import file_open
from odoo.tools.safe_eval import safe_eval

from .. import version as studio_version
from .code_generator_writer import project_migration_file

_logger = logging.getLogger(__name__)

PARAM_DEFAULT_DESTINATION = "erplibre_studio.default_destination"
# The file written into a generated module that names the project and the
# database it comes from.
MARKER_FILE = ".erplibre_studio"

# The fields of a project only its own methods write: they decide what the
# generation may replace on the disk.
GENERATION_MANAGED_FIELDS = frozenset(
    {
        "generated_snapshot",
        "generated_date",
        "generated_path",
        "generated_version",
        "generation_count",
        "generation_log",
        "code_generator_id",
    }
)

# Characters the code generator copies unescaped into a quoted Python
# string of the generated module: refused in the texts that reach it.
_UNSAFE_TEXT = ("'", '"', "\\", "\n", "\r")


def _series():
    return release.major_version


class ErplibreStudioProject(models.Model):
    """The generation of a studio project as a module, by code_generator:
    once applied, then again at each new version, into an addons
    repository of the running Odoo version."""

    _inherit = "erplibre.studio.project"

    summary = fields.Char()
    description = fields.Text(help="Written in the readme of the generated module.")
    author = fields.Char(default=lambda self: self.env.company.name)
    license = fields.Selection(
        [("AGPL-3", "AGPL-3"), ("LGPL-3", "LGPL-3")],
        default="AGPL-3",
        required=True,
    )
    destination = fields.Selection(
        selection="_selection_destination",
        default=lambda self: self._default_destination(),
        help="The addons repository of the running Odoo version, from the "
        "last ERPLibre snapshot, where the module is generated.",
    )
    version = fields.Char(
        default=lambda self: f"{_series()}.1.0.0",
        required=True,
        help="Version of the next generation: kept when it is above the "
        "last generated version, else its patch number moves up.",
    )
    # Without this module, a generated project is applied: its changes are
    # the ones in the database.
    state = fields.Selection(
        selection_add=[("generated", "Generated")],
        ondelete={
            "generated": lambda records: records._internal().write({"state": "applied"})
        },
    )
    generated_snapshot = fields.Text(readonly=True, copy=False)
    generated_date = fields.Datetime(readonly=True, copy=False)
    generated_path = fields.Char(readonly=True, copy=False)
    generated_version = fields.Char(readonly=True, copy=False)
    generation_count = fields.Integer(readonly=True, copy=False)
    generation_log = fields.Text(readonly=True, copy=False)
    code_generator_id = fields.Many2one(
        "code.generator.module", readonly=True, copy=False, ondelete="set null"
    )

    # ── fields ──────────────────────────────────────────────────────────

    @api.model
    def _destination_choices(self):
        """[(path, label)]: the addons repositories of the running Odoo
        version in the last ERPLibre snapshot, paths relative to the
        checkout."""
        snapshot = self.env["erplibre.code.snapshot"].sudo().search([], limit=1)
        lines = snapshot.repo_ids.filtered(
            lambda r: r.is_active_version and "/addons/" in f"/{r.path}"
        )
        return [(line.path, line.path) for line in lines.sorted("path")]

    @api.model
    def _selection_destination(self):
        return self._destination_choices()

    @api.model
    def _default_destination(self):
        value = (
            self.env["ir.config_parameter"].sudo().get_param(PARAM_DEFAULT_DESTINATION)
        )
        choices = [path for path, _label in self._destination_choices()]
        return value if value in choices else False

    @api.model
    def _managed_fields(self):
        return super()._managed_fields() | GENERATION_MANAGED_FIELDS

    def _applied_state(self, snapshot):
        if self.generated_snapshot == snapshot:
            return "generated"
        return super()._applied_state(snapshot)

    # ── constraints ─────────────────────────────────────────────────────

    @api.constrains("module_name")
    def _check_module_name(self):
        super()._check_module_name()
        for project in self:
            generator = (
                self.env["code.generator.module"]
                .sudo()
                .search(
                    [
                        ("name", "=", project.module_name),
                        ("id", "!=", project.code_generator_id.id),
                    ]
                )
            )
            if generator:
                raise ValidationError(
                    self.env._(
                        "The code generator already has a module named %(name)s.",
                        name=project.module_name,
                    )
                )

    @api.constrains("version")
    def _check_version(self):
        for project in self:
            if not studio_version.valid_version(project.version, _series()):
                raise ValidationError(
                    self.env._(
                        "The version %(version)s must have 5 parts and start "
                        "with %(series)s.",
                        version=project.version,
                        series=_series(),
                    )
                )

    @api.constrains("name", "summary", "author")
    def _check_manifest_text(self):
        for project in self:
            for value in (project.name, project.summary, project.author):
                if value and any(char in value for char in _UNSAFE_TEXT):
                    raise ValidationError(
                        self.env._(
                            "The name, summary and author cannot contain quotes, "
                            "backslashes or line breaks: %(value)s",
                            value=value,
                        )
                    )

    @api.model
    def _check_field_texts(self, label, help_text):
        """The label and the tooltip of a new field, and the label of a new
        model, go into a quoted Python string of the generated module."""
        super()._check_field_texts(label, help_text)
        for value in (label, help_text):
            if any(char in value for char in _UNSAFE_TEXT):
                raise UserError(
                    self.env._(
                        "The labels and tooltips of new fields and models "
                        "cannot contain quotes, backslashes or line breaks: "
                        "%(value)s",
                        value=value,
                    )
                )

    def _check_generation_texts(self):
        """The checks of ``_check_manifest_text`` and ``_check_field_texts``
        again, on the texts as they are: a project recorded before this
        module was installed went through none of them. The label of a new
        model becomes its ``_description``."""
        self.ensure_one()
        self._check_manifest_text()
        for line in self.new_model_ids:
            self._check_field_texts((line.name or "").strip(), "")
        for change in self._project_field_changes():
            definition = change._payload().get("field") or {}
            self._check_field_texts(
                definition.get("field_description") or "",
                definition.get("help") or "",
            )

    @api.model
    def _arch_message(self, exc):
        if getattr(exc, "code", None) == "invalid_version":
            return self.env._("Invalid version %(version)s.", **exc.params)
        return super()._arch_message(exc)

    def write(self, vals):
        if "module_name" in vals:
            for project in self:
                renamed = project.module_name != vals["module_name"]
                if renamed and project.generation_count:
                    raise UserError(
                        self.env._(
                            "The technical name of a generated module cannot change."
                        )
                    )
        return super().write(vals)

    def unlink(self):
        generators = self.mapped("code_generator_id")
        res = super().unlink()
        # ir.model.m2o_module cascades: a generator still linked to a model
        # would delete that model with it.
        self.env["ir.model"].sudo().search(
            [("m2o_module", "in", generators.ids)]
        ).write({"m2o_module": False})
        generators.sudo().unlink()
        return res

    # ── guards ──────────────────────────────────────────────────────────

    @api.model
    def _check_studio_disk(self):
        """The erplibre_info guard of the actions that write to the disk."""
        self.env["erplibre.developer"]._check_server_actions()

    # ── generation ──────────────────────────────────────────────────────

    def _destination_path(self):
        """The absolute directory the module goes into, checked against the
        destination choices."""
        self.ensure_one()
        choices = [path for path, _label in self._destination_choices()]
        if not self.destination or self.destination not in choices:
            raise UserError(
                self.env._(
                    "Choose a destination among the addons repositories of the "
                    "last ERPLibre snapshot."
                )
            )
        root = runner.erplibre_root(self.env) or ""
        path = os.path.realpath(os.path.join(root, self.destination))
        if not os.path.isdir(path):
            raise UserError(
                self.env._("The destination %(path)s is not a directory.", path=path)
            )
        return path

    def _generation_models(self):
        """The models of the generated module: the new models and the
        models the new fields extend."""
        return sorted(
            set(self._project_field_changes().mapped("model"))
            | self._studio_new_models()
        )

    def _rule_domain_fields(self, rule):
        """The fields that the domain of ``rule`` names first in each of its
        paths, as ir.model.fields records of its model."""
        Fields = self.env["ir.model.fields"].sudo()
        try:
            domain = safe_eval(
                rule.domain_force or "[]", self.env["ir.rule"]._eval_context()
            )
        except Exception:  # Apply refuses such a domain; it names no field.
            return Fields
        for term in domain if isinstance(domain, (list, tuple)) else []:
            if isinstance(term, (list, tuple)) and len(term) == 3:
                path = term[0]
                if isinstance(path, str):
                    Fields |= Fields._get(rule.model, path.split(".")[0])
        return Fields

    def _view_type_module(self, view_type):
        """The module that adds ``view_type`` to ir.ui.view (web_timeline
        for « timeline »), from the external id of the selection value."""
        value = (
            self.env["ir.model.fields.selection"]
            .sudo()
            .search(
                [
                    ("field_id.model", "=", "ir.ui.view"),
                    ("field_id.name", "=", "type"),
                    ("value", "=", view_type),
                ],
                limit=1,
            )
        )
        return (
            self._module_of("ir.model.fields.selection", value.id) if value else False
        )

    def _dependencies(self):
        """The modules the generated module depends on: those of the edited
        views, of their view types and of the nodes the changes locate
        (read from the branding of the combined arch), of the models
        extended, of the fields added or named by the changes (a filter
        domain, a group-by, a timeline date) and of the comodels; mail for
        a chatter; those of the parent menus, of the groups and of the
        existing models of the access rights and record rules, and of the
        fields their domains name."""
        self.ensure_one()
        IrModel = self.env["ir.model"].sudo()
        names = {"base"}
        view_modules = {}

        def module_of_view(view_id):
            if view_id not in view_modules:
                view_modules[view_id] = self._module_of("ir.ui.view", view_id)
            return view_modules[view_id]

        def node_module(node):
            for item in [node, *node.iterancestors()]:
                if item.get("data-oe-id"):
                    return module_of_view(int(item.get("data-oe-id")))
            return False

        Fields = self.env["ir.model.fields"].sudo()
        for view in self.change_ids.mapped("view_id"):
            names.add(module_of_view(view.id))
            names.add(self._view_type_module(view.type))
            current = self._base_arch(view, branding=True)
            for change in self._view_changes(view):
                data = change._as_dict()
                for xpath in (data["xpath"], data["payload"].get("source")):
                    if not xpath:
                        continue
                    nodes = current.xpath(xpath)
                    if nodes and hasattr(nodes[0], "tag"):
                        names.add(node_module(nodes[0]))
                current, _errors = studio_arch.apply_changes(current, [data], view.type)
                named = list(data["payload"].get("fields") or [])
                if change.change_type == "add_existing_field":
                    named.append(change.field_name)
                for name in named:
                    field = Fields._get(change.model, name)
                    if field:
                        names.add(self._module_of("ir.model.fields", field.id))
        for change in self._project_field_changes():
            names.add(self._module_of("ir.model", IrModel._get_id(change.model)))
            relation = change._payload()["field"].get("relation")
            if relation:
                names.add(self._module_of("ir.model", IrModel._get_id(relation)))
        names |= self._model_line_dependencies()
        names.discard(False)
        names.discard(self.module_name)
        return sorted(names)

    def _model_line_dependencies(self):
        """The modules the new models, the access rights and the record
        rules of the project need: mail for a chatter, those of the parent
        menus, of the groups, of the existing models and of the fields the
        domains name. A set that may hold False."""
        IrModel = self.env["ir.model"].sudo()
        names = set()
        if self.new_model_ids.filtered("chatter"):
            names.add("mail")
        for menu in self.new_model_ids.filtered(
            lambda m: m.menu_mode == "menu"
        ).menu_parent_id:
            names.add(self._module_of("ir.ui.menu", menu.id))
        for group in self.access_line_ids.group_id | self.rule_line_ids.group_ids:
            names.add(self._module_of("res.groups", group.id))
        models_named = set(self.access_line_ids.mapped("model"))
        models_named |= set(self.rule_line_ids.mapped("model"))
        for model in models_named - self._studio_new_models():
            names.add(self._module_of("ir.model", IrModel._get_id(model)))
        for rule in self.rule_line_ids:
            for field in self._rule_domain_fields(rule):
                names.add(self._module_of("ir.model.fields", field.id))
        return names

    def _code_generator_module(self, dependencies):
        """The code.generator.module of the project, created or updated. Its
        icon is the one of the app of the project, else the studio's; it is
        an application when it has an app."""
        self.ensure_one()
        has_app = bool(self.new_model_ids.filtered(lambda m: m.menu_mode == "app"))
        icon_module = "erplibre_studio"
        if has_app and self.app_icon:
            icon_module = self._studio_icon_module(self.app_icon)
        with file_open(f"{icon_module}/static/description/icon.png", "rb") as icon:
            icon_data = base64.b64encode(icon.read())
        vals = {
            "name": self.module_name,
            "shortdesc": self.name,
            "summary": self.summary or self.name,
            "author": self.author or False,
            "license": self.license,
            "enable_sync_code": False,
            "icon_real_image": icon_data,
            "application": has_app,
        }
        Generator = self.env["code.generator.module"].sudo()
        generator = self.code_generator_id.sudo()
        if generator:
            generator.write(vals)
        else:
            generator = Generator.create([vals])
            self._internal().code_generator_id = generator
        generator.dependencies_id.filtered(
            lambda d: d.depend_id.name not in dependencies
        ).unlink()
        generator.add_module_dependency(dependencies)
        missing = self._missing_dependencies(generator, dependencies)
        if missing:
            # code_generator links the modules of ir.module.module only: a
            # module generated since the last update of the list is not
            # there yet.
            self.env["ir.module.module"].sudo().update_list()
            generator.add_module_dependency(dependencies)
            missing = self._missing_dependencies(generator, dependencies)
        if missing:
            raise UserError(
                self.env._(
                    "The module depends on %(modules)s, which this server does "
                    "not know: generate them into the addons path first.",
                    modules=", ".join(missing),
                )
            )
        return generator

    @api.model
    def _missing_dependencies(self, generator, dependencies):
        """The names of ``dependencies`` the generator does not depend on."""
        linked = set(generator.dependencies_id.depend_id.mapped("name"))
        return sorted(set(dependencies) - linked)

    @contextmanager
    def _generator_scope(self, generator):
        """Link the models of the project to ``generator`` for the time of
        one generation, then restore their links. code_generator reads
        ``ir.model.m2o_module``, one generator per model; and that link
        cascades on delete. A model the project extends inherits itself;
        a new model inherits the mail mixins of its chatter, or nothing,
        which makes it a model of its own (``_name``)."""
        IrModel = self.env["ir.model"].sudo()
        records = IrModel.browse(
            [IrModel._get_id(name) for name in self._generation_models()]
        )
        chatter = set(self.new_model_ids.filtered("chatter").mapped("model"))
        new_models = self._studio_new_models()
        saved = [(m, m.m2o_module, m.inherit_model_ids) for m in records]
        Dependency = self.env["code.generator.ir.model.dependency"].sudo()
        created = Dependency
        cursor = self.env.cr
        try:
            for record in records:
                if record.model not in new_models:
                    parents = [record.id]
                elif record.model in chatter:
                    parents = [
                        IrModel._get_id("mail.thread"),
                        IrModel._get_id("mail.activity.mixin"),
                    ]
                else:
                    parents = []
                created_one = Dependency.create(
                    [{"depend_id": parent} for parent in parents]
                )
                created |= created_one
                record.write(
                    {
                        "m2o_module": generator.id,
                        "inherit_model_ids": [(6, 0, created_one.ids)],
                    }
                )
            generator.invalidate_recordset(["o2m_models", "installed_version"])
            # code_generator keeps its file state on the cursor.
            if hasattr(cursor, "_code_generator_data"):
                del cursor._code_generator_data
            yield
        finally:
            if hasattr(cursor, "_code_generator_data"):
                del cursor._code_generator_data
            for record, owner, inherits in saved:
                record.write(
                    {
                        "m2o_module": owner.id,
                        "inherit_model_ids": [(6, 0, inherits.ids)],
                    }
                )
            created.exists().unlink()
            generator.invalidate_recordset(["o2m_models"])

    def _readme(self, version):
        """The DESCRIPTION.md of the generated module."""
        lines = [
            self.description.strip() if self.description else self.name,
            "",
            self.env._("Changes made with ERPLibre studio:"),
            "",
        ]
        for change in self._project_field_changes():
            definition = change._payload()["field"]
            lines.append(
                f"- `{change.model}`: field `{change.field_name}` "
                f"({definition['ttype']}, {definition['field_description']})"
            )
        for view in self.change_ids.mapped("view_id"):
            count = len(self._view_changes(view))
            lines.append(
                f"- {view.type} view `{view.xml_id or view.name}`: "
                + self.env._("%(count)s change(s)", count=count)
            )
        for line in self.new_model_ids:
            label = (line.menu_name or "").strip() or line.name.strip()
            if line.menu_mode == "app":
                text = self.env._(
                    "new model, menu %(menu)s in the app %(app)s",
                    menu=label,
                    app=self.app_name,
                )
            else:
                text = self.env._(
                    "new model, menu %(menu)s under %(parent)s",
                    menu=label,
                    parent=line.menu_parent_id.complete_name,
                )
            if line.chatter:
                text += ", " + self.env._("with a chatter")
            lines.append(f"- `{line.model}` ({line.name.strip()}): {text}")
        for access in self.access_line_ids:
            perms = "".join(
                letter if access[perm] else "-"
                for letter, perm in zip("rwcd", studio_perms, strict=True)
            )
            lines.append(
                f"- `{access.model}`: "
                + self.env._(
                    "access right %(perms)s for %(group)s",
                    perms=perms,
                    group=access.group_id.full_name,
                )
            )
        for rule in self.rule_line_ids:
            groups = ", ".join(rule.group_ids.mapped("full_name"))
            lines.append(
                f"- `{rule.model}`: "
                + self.env._(
                    "record rule %(name)s for %(groups)s: `%(domain)s`",
                    name=rule.name,
                    groups=groups or self.env._("every user"),
                    domain=rule.domain_force,
                )
            )
        return "\n".join(lines) + "\n"

    def _marker_text(self):
        """The content of ``MARKER_FILE``: a digest of the database, the
        project and the module, that names none of them."""
        self.ensure_one()
        uuid = self.env["ir.config_parameter"].sudo().get_param("database.uuid")
        key = f"{uuid}:{self.id}:{self.module_name}"
        return hashlib.sha256(key.encode()).hexdigest() + "\n"

    def _is_own_directory(self, path):
        """Whether ``path`` holds a module this project generated in this
        database: its ``MARKER_FILE`` matches. A path stored on the project
        proves nothing, the marker is on the disk."""
        self.ensure_one()
        marker = os.path.join(path, MARKER_FILE)
        try:
            with open(marker, encoding="utf-8") as fh:
                return fh.read() == self._marker_text()
        except OSError:
            return False

    def action_generate(self):
        """Generate the module with code_generator into the destination,
        replacing the previous generation of this project only. The version
        is the one of the project when it is above the last generated one,
        else the next patch version. Writes to the disk: erplibre_info
        guard."""
        self.ensure_one()
        self._check_studio_access()
        self._check_studio_disk()
        self._update_state()
        if not self.item_count:
            raise UserError(self.env._("The project has no change to generate."))
        self._check_generation_texts()
        if self.state == "draft":
            raise UserError(self.env._("Apply the draft before generating the module."))
        missing = self.change_ids.mapped("view_id").filtered(lambda v: not v.xml_id)
        if missing:
            raise UserError(
                self.env._(
                    "A generated module inherits views by their external id; "
                    "these views have none: %(views)s",
                    views=", ".join(missing.mapped("name")),
                )
            )
        parent = self._destination_path()
        target = os.path.join(parent, self.module_name)
        if os.path.lexists(target) and (
            os.path.islink(target)
            or not os.path.isdir(target)
            or not self._is_own_directory(target)
        ):
            raise UserError(
                self.env._(
                    "%(path)s exists and was not generated by this project.",
                    path=target,
                )
            )
        try:
            version = studio_version.next_version(self.version, self.generated_version)
        except studio_arch.ArchError as exc:
            raise UserError(self._arch_message(exc)) from exc
        started = time.monotonic()
        dependencies = self._dependencies()
        generator = self._code_generator_module(dependencies)
        with self._generator_scope(generator):
            writer = (
                self.env["code.generator.writer"]
                .sudo()
                .with_context(
                    erplibre_studio_project_id=self.id,
                    erplibre_studio_version=version,
                )
                .create([{"code_generator_ids": generator.ids}])
            )
        rootdir = writer.rootdir
        try:
            readme = os.path.join(rootdir, "readme")
            os.makedirs(readme, exist_ok=True)
            with open(
                os.path.join(readme, "DESCRIPTION.md"), "w", encoding="utf-8"
            ) as fh:
                fh.write(self._readme(version))
            with open(os.path.join(rootdir, MARKER_FILE), "w", encoding="utf-8") as fh:
                fh.write(self._marker_text())
            if self.new_model_ids:
                # An upgrade to this version takes over the models Apply
                # created since the module was installed (hooks.py).
                migration = os.path.join(rootdir, "migrations", version)
                os.makedirs(migration, exist_ok=True)
                with open(
                    os.path.join(migration, "pre-migration.py"), "w", encoding="utf-8"
                ) as fh:
                    fh.write(project_migration_file(self, self.license))
            files = sorted(
                os.path.relpath(os.path.join(base, name), rootdir)
                for base, _dirs, names in os.walk(rootdir)
                for name in names
                if not name.endswith(".pyc")
            )
            if os.path.exists(target):
                shutil.rmtree(target)
            shutil.copytree(
                rootdir, target, ignore=shutil.ignore_patterns("__pycache__")
            )
        finally:
            # The writer works in a mkdtemp() directory of its own.
            shutil.rmtree(os.path.dirname(rootdir), ignore_errors=True)
        duration = time.monotonic() - started
        log = [
            f"version: {version}",
            f"destination: {target}",
            f"depends: {', '.join(dependencies)}",
            f"duration: {duration:.1f} s",
            "files:",
            *[f"  {name}" for name in files],
        ]
        # The external ids of the module are in its files now: an upgrade
        # updates their records, and deletes those its files lose.
        self.env["ir.model.data"].sudo().search(
            [("module", "=", self.module_name), ("noupdate", "=", True)]
        ).write({"noupdate": False})
        self._internal().write(
            {
                "version": version,
                "generated_version": version,
                "generation_count": self.generation_count + 1,
                "generated_date": fields.Datetime.now(),
                "generated_path": target,
                "generated_snapshot": self._current_snapshot(),
                "generation_log": "\n".join(log),
            }
        )
        self._update_state()
        if parent in [os.path.realpath(p) for p in odoo.addons.__path__]:
            self.env["ir.module.module"].sudo().update_list()
        _logger.info(
            "Studio module %s %s generated in %s",
            self.module_name,
            version,
            target,
        )
        return True

    def action_install_module(self):
        """Install the generated module in this database, on request, once
        it holds the last Apply: installing a module older than the
        database would delete what Apply made since (the external ids of
        the module its files do not hold)."""
        self.ensure_one()
        self._check_studio_access()
        self._check_studio_disk()
        self._update_state()
        if self.state != "generated":
            raise UserError(
                self.env._(
                    "Generate the module again first: the database holds "
                    "changes the module on the disk does not have."
                )
            )
        Module = self.env["ir.module.module"].sudo()
        module = Module.search([("name", "=", self.module_name)])
        if not module:
            Module.update_list()
            module = Module.search([("name", "=", self.module_name)])
        if not module:
            raise UserError(
                self.env._(
                    "%(name)s is not on the addons path of this server.",
                    name=self.module_name,
                )
            )
        if module.state == "installed":
            raise UserError(self.env._("The module is already installed."))
        return module.button_immediate_install()
