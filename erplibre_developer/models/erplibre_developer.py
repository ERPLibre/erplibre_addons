# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import os

import odoo
from lxml import etree
from odoo import api, models
from odoo.addons.erplibre_info import runner
from odoo.addons.erplibre_info.models.erplibre_code_snapshot import safe_version
from odoo.exceptions import AccessError, UserError
from odoo.modules.module import get_manifest, get_module_path

from .. import code, introspection

VIEW_TYPES = ("form", "list", "kanban", "search", "pivot", "graph", "calendar")
VIEW_TYPES += ("activity", "gantt", "timeline", "map", "cohort", "hierarchy")
COMMIT_LIMIT = 20


class ErplibreDeveloper(models.AbstractModel):
    """The server side of the developer panel: introspection of the view
    shown in the web client, the code behind it, and the developer
    actions. Every public method requires the Settings group and the
    developer mode; the actions that change the server also require the
    odoo.conf flag of erplibre_info."""

    _name = "erplibre.developer"
    _description = "ERPLibre developer panel"

    # ── guards ──────────────────────────────────────────────────────────

    @api.model
    def _check_panel_access(self):
        """Raise unless the user is a Settings administrator in developer
        mode: the panel reads file paths and the code of the server."""
        if not self.env.user.has_group("base.group_system"):
            raise AccessError(
                self.env._("Only the Settings administrators open the developer panel.")
            )
        if not self.env["erplibre.code.run"]._is_debug_mode():
            raise UserError(
                self.env._("The developer panel requires the developer mode.")
            )

    @api.model
    def _check_server_actions(self):
        """The guard of the erplibre_info server actions: odoo.conf flag,
        Settings group, developer mode."""
        self.env["erplibre.code.run"]._check_server_actions()

    # ── IDE hook ────────────────────────────────────────────────────────

    @api.model
    def _ide_available(self):
        """Whether a module registered an IDE opener. A bridge module
        overrides it with ``_ide_open``."""
        return False

    @api.model
    def _ide_open(self, path, line):
        raise UserError(self.env._("No IDE is configured on this server."))

    @api.model
    def action_open_in_ide(self, path, line=0):
        """Open ``path`` at ``line`` in the IDE of the server. The file must
        be a source file of the running code."""
        self._check_panel_access()
        self._check_server_actions()
        if not self._ide_available():
            raise UserError(self.env._("No IDE is configured on this server."))
        real = self._source_file(path)
        return self._ide_open(real, max(0, int(line or 0)))

    @api.model
    def _source_roots(self):
        """The directories whose files the panel may name: the addons
        path, the Odoo package and the ERPLibre checkout."""
        roots = [os.path.dirname(odoo.__file__)]
        roots += list(odoo.addons.__path__)
        root = runner.erplibre_root(self.env)
        if root:
            roots.append(root)
        return [os.path.realpath(r) for r in roots if r]

    @api.model
    def _source_file(self, path):
        """The real path of ``path``; raise unless it is a file under one
        of ``_source_roots``."""
        real = os.path.realpath(path or "")
        if not os.path.isfile(real) or not any(
            real.startswith(root + os.sep) for root in self._source_roots()
        ):
            raise UserError(
                self.env._("%(path)s is not a source file of this server.", path=path)
            )
        return real

    # ── introspection payload ───────────────────────────────────────────

    @api.model
    def _location(self, path, line, root):
        return {
            "file": path or False,
            "file_rel": code.relative_to(path, root) if path else False,
            "line": line or 0,
        }

    @api.model
    def _view_entry(self, view, cache, root, current):
        path, line = introspection.view_location(view, cache)
        specs, touched = (
            introspection.view_specs(view.arch) if view.inherit_id else ([], [])
        )
        xml_id = view.xml_id or False
        entry = {
            "id": view.id,
            "name": view.name,
            "xml_id": xml_id,
            "module": xml_id.split(".", 1)[0] if xml_id else False,
            "model": view.model,
            "type": view.type,
            "priority": view.priority,
            "mode": view.mode,
            "active": view.active,
            "inherit_id": view.inherit_id.id or False,
            "inherit_name": view.inherit_id.xml_id or view.inherit_id.name or False,
            "groups": view.groups_id.mapped("full_name"),
            "is_current": view == current,
            "specs": specs,
            "fields": touched,
            "arch": view.arch,
        }
        entry.update(self._location(path, line, root))
        return entry

    @api.model
    def _resolve_view(self, model, view_id, view_type):
        View = self.env["ir.ui.view"]
        view = View.browse(int(view_id)).exists() if view_id else View
        if not view:
            view = View.browse(View.default_view(model, view_type))
        return view

    @api.model
    def get_view_info(self, model, view_id=False, view_type="form", action_id=False):
        """The introspection payload of a view shown in the web client.

        ``view_id`` False takes the default view of ``model`` for
        ``view_type``. Return a dict: ``view`` (the view shown), ``views``
        (every view combined into it, in application order),
        ``combined_arch``, ``fields`` (the fields of ``model`` the arch
        shows, with the modules that define and override them),
        ``modules`` (every module named), ``action`` and the flags of the
        developer actions. No git call, no script: the code tab loads
        with ``get_code_info``.
        """
        self._check_panel_access()
        if model not in self.env:
            raise UserError(self.env._("Unknown model %(model)s.", model=model))
        if view_type not in VIEW_TYPES:
            raise UserError(self.env._("Unknown view type %(type)s.", type=view_type))
        Model = self.env[model]
        cache = introspection.SourceCache()
        root = runner.erplibre_root(self.env)
        view = self._resolve_view(model, view_id, view_type)
        views = []
        if view:
            arch_tree = view._get_combined_arch()
            views = [
                self._view_entry(v, cache, root, view)
                for v in introspection.applied_views(view)
            ]
        else:
            # A model without a view of this type: Odoo builds a default one.
            arch_tree, _view = Model._get_view(False, view_type)
        combined = etree.tostring(arch_tree, encoding="unicode", pretty_print=True)
        onchanges = introspection.decorated_methods(Model, "_onchange")
        constrains = introspection.decorated_methods(Model, "_constrains")
        fields_info = []
        for node in introspection.arch_fields(arch_tree):
            if node["name"] not in Model._fields:
                continue
            info = introspection.field_origins(
                Model, node["name"], cache, onchanges, constrains
            )
            info["node"] = node
            for entry in [*info["definitions"], *info["overrides"]]:
                entry.update(self._location(entry["file"], entry["line"], root))
            fields_info.append(info)
        modules = set()
        for entry in views:
            if entry["module"]:
                modules.add(entry["module"])
        for info in fields_info:
            for entry in [*info["definitions"], *info["overrides"]]:
                if entry["module"]:
                    modules.add(entry["module"])
        installed = set(
            self.env["ir.module.module"]
            .sudo()
            .search([("name", "in", list(modules)), ("state", "=", "installed")])
            .mapped("name")
        )
        current = next((v for v in views if v["is_current"]), None)
        allowed = self.env["erplibre.code.run"]._server_actions_allowed()
        return {
            "model": model,
            "model_name": self.env["ir.model"]._get(model).name,
            "view_type": view_type,
            "view": current,
            "views": views,
            "combined_arch": combined,
            "fields": fields_info,
            "modules": sorted(m for m in modules if m in installed),
            "action": self._action_info(action_id),
            "server_actions_allowed": allowed,
            # Opening the IDE is a server action: offered only when allowed.
            "ide_available": allowed and self._ide_available(),
        }

    @api.model
    def _action_info(self, action_id):
        if not action_id:
            return False
        action = self.env["ir.actions.actions"].browse(int(action_id)).exists()
        if not action:
            return False
        # The external id belongs to the concrete action model.
        if action.type in self.env:
            action = self.env[action.type].browse(action.id)
        xml_id = action.get_external_id().get(action.id) or False
        return {
            "id": action.id,
            "name": action.name,
            "type": action.type,
            "xml_id": xml_id,
            "module": xml_id.split(".", 1)[0] if xml_id else False,
        }

    # ── code and repositories ───────────────────────────────────────────

    @api.model
    def _repo_state_labels(self):
        """{state: label} of the repository states, in the user's language."""
        field = self.env["erplibre.code.snapshot.repo"]._fields["state"]
        return dict(field._description_selection(self.env))

    @api.model
    def _repo_vals(self, line, labels=None):
        """The repository part of the code payload, from a snapshot line of
        erplibre_info or a ``repo_state.py`` entry (a dict)."""
        if labels is None:
            labels = self._repo_state_labels()
        get = line.get if isinstance(line, dict) else line.__getitem__
        state = get("state") or False
        return {
            "path": get("path") or False,
            "state": state,
            "state_label": labels.get(state, state) if state else False,
            "branch": get("branch") or False,
            "head": get("head") or False,
            "dirty": bool(get("dirty")),
            "revision": get("revision") or False,
            "manifest_branch": get("manifest_branch") or False,
            "error": get("error") or False,
        }

    @api.model
    def get_code_info(self, modules, refresh=False):
        """The code behind ``modules``: for each one its path, versions and
        the state of its git repository.

        The state comes from the last erplibre_info snapshot; a module
        that no snapshot links, or every module with ``refresh``, is read
        with one ``repo_state.py snapshot --repo …`` call for all of their
        repositories. Without a checkout, the snapshot stays the only
        source, ``refresh`` or not, and ``error`` says why. Return
        {modules: [...], snapshot_date, error}.
        """
        self._check_panel_access()
        root = runner.erplibre_root(self.env)
        labels = self._repo_state_labels()
        records = {
            m.name: m
            for m in self.env["ir.module.module"]
            .sudo()
            .search([("name", "in", list(modules or []))])
        }
        snapshot = self.env["erplibre.code.snapshot"].search([], limit=1)
        lines = {
            line.name: line.repo_line_id
            for line in snapshot.module_ids
            if line.name in records and line.repo_line_id
        }
        result = []
        to_read = {}
        for name in modules or []:
            record = records.get(name)
            path = get_module_path(name, display_warning=False) or False
            path = os.path.realpath(path) if path else False
            clone = code.repository_of(path, root) if path else None
            manifest = get_manifest(name) if path else {}
            entry = {
                "name": name,
                "state": record.state if record else False,
                "installed_version": (record.latest_version if record else False)
                or False,
                "code_version": safe_version(manifest.get("version")) or False,
                "path": path,
                "path_rel": code.relative_to(path, root) if path else False,
                "clone": clone or False,
                "clone_rel": code.relative_to(clone, root) if clone else False,
                "module_rel": os.path.relpath(path, clone) if clone else False,
                "repo": False,
                "repo_source": False,
            }
            line = lines.get(name)
            if line and (not refresh or not root):
                entry["repo"] = self._repo_vals(line, labels)
                entry["repo_source"] = "snapshot"
            elif clone and root and entry["clone_rel"] != clone:
                to_read.setdefault(entry["clone_rel"], []).append(entry)
            result.append(entry)
        error = False if root else runner.checkout_problem(self.env)
        if to_read:
            error = self._read_repos(to_read, labels)
        return {
            "modules": result,
            "snapshot_date": snapshot.date if snapshot else False,
            "error": error,
        }

    @api.model
    def _read_repos(self, to_read, labels=None):
        """Fill the ``repo`` of the entries of ``to_read`` ({repository path
        relative to the checkout: [entry]}) with one ``repo_state.py``
        call. Return the error message, or False."""
        args = ["snapshot"]
        for rel in sorted(to_read):
            args += ["--repo", rel]
        try:
            res = runner.run_json(self.env, runner.SCRIPT_STATE, args)
        except runner.RunnerError as exc:
            return str(exc)
        by_path = {r.get("path"): r for r in res.data.get("repos") or []}
        for rel, entries in to_read.items():
            repo = by_path.get(rel)
            for entry in entries:
                if repo:
                    entry["repo"] = self._repo_vals(repo, labels)
                    entry["repo_source"] = "repo_state"
        return False

    @api.model
    def get_module_commits(self, module, limit=COMMIT_LIMIT):
        """The last ``limit`` commits that touch the directory of
        ``module`` in its git clone: {module, clone_rel, commits, error}."""
        self._check_panel_access()
        root = runner.erplibre_root(self.env)
        path = get_module_path(module, display_warning=False)
        if not path:
            raise UserError(self.env._("Module %(module)s not found.", module=module))
        path = os.path.realpath(path)
        clone = code.repository_of(path, root)
        result = {
            "module": module,
            "clone_rel": code.relative_to(clone, root) if clone else False,
            "commits": [],
            "error": False,
        }
        if not clone:
            result["error"] = self.env._("The module is not in a git clone.")
            return result
        try:
            result["commits"] = code.git_log(
                self.env, clone, os.path.relpath(path, clone), limit
            )
        except code.GitLogError as exc:
            result["error"] = str(exc)
        return result

    # ── developer actions ───────────────────────────────────────────────

    @api.model
    def action_upgrade_module(self, module):
        """Open the erplibre_info confirmation that marks ``module`` to
        upgrade and restarts the server: the upgrade then runs at the next
        start, with the code on disk (see
        ``erplibre.code.run._request_restart``)."""
        self._check_panel_access()
        self._check_server_actions()
        record = (
            self.env["ir.module.module"]
            .sudo()
            .search([("name", "=", module), ("state", "=", "installed")], limit=1)
        )
        if not record:
            raise UserError(
                self.env._("Module %(module)s is not installed.", module=module)
            )
        return self.env["erplibre.code.confirm.wizard"]._action_open(
            "restart_upgrade", modules=record
        )

    @api.model
    def action_reload_assets(self):
        """Delete the generated asset bundles: the next page load builds
        them from the files on disk."""
        self._check_panel_access()
        self.env["ir.attachment"].sudo().regenerate_assets_bundles()
        return True
