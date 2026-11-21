# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import os

import odoo
from lxml import etree
from odoo import api, models
from odoo.addons.erplibre_info import runner
from odoo.addons.erplibre_info_git.models.erplibre_code_snapshot import safe_version
from odoo.exceptions import AccessError, UserError
from odoo.modules.module import get_manifest, get_module_path

from .. import code, introspection

VIEW_TYPES = ("form", "list", "kanban", "search", "pivot", "graph", "calendar")
VIEW_TYPES += ("activity", "gantt", "timeline", "map", "cohort", "hierarchy")
COMMIT_LIMIT = 20
RUN_LIMIT = 5
RUN_LIMIT_MAX = 50


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
        ``combined_arch``, ``combined_lines`` (the same arch line by line
        with the module of each node, ``introspection.combined_lines``;
        False when it cannot be built), ``fields`` (the fields of
        ``model`` the arch shows, with the modules that define and
        override them, and in ``view_ids`` the views that show, add or
        target them),
        ``modules`` (every installed module named), ``module_versions``
        (``_module_versions``), ``action``, the flags of the developer
        actions with ``server_actions_checks``, and ``snapshot_date``, the
        date of the last erplibre_info_git snapshot. No git call, no
        script: the code tab loads with ``get_code_info``.
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
        touching = {}
        lines = False
        if view:
            arch_tree = view._get_combined_arch()
            chain = introspection.applied_views(view)
            for applied in chain:
                entry = self._view_entry(applied, cache, root, view)
                views.append(entry)
                # The root of the chain shows its fields with its own arch;
                # an extension names those its specs add or target.
                names = (
                    entry["fields"]
                    if applied.inherit_id
                    else introspection.arch_field_names(applied.arch)
                )
                for name in names:
                    touching.setdefault(name, []).append(applied.id)
            lines = introspection.combined_lines(
                chain, {entry["id"]: entry["module"] for entry in views}, arch_tree
            )
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
            info["view_ids"] = touching.get(node["name"], [])
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
        modules = sorted(m for m in modules if m in installed)
        snapshot = self.env["erplibre.code.snapshot"].search([], limit=1)
        return {
            "model": model,
            "model_name": self.env["ir.model"]._get(model).name,
            "view_type": view_type,
            "view": current,
            "views": views,
            "combined_arch": combined,
            "combined_lines": lines,
            "fields": fields_info,
            "modules": modules,
            "module_versions": self._module_versions(modules),
            "action": self._action_info(action_id),
            "server_actions_allowed": allowed,
            "server_actions_checks": self._server_actions_checks(),
            "snapshot_date": snapshot.date if snapshot else False,
            # Opening the IDE is a server action: offered only when allowed.
            "ide_available": allowed and self._ide_available(),
        }

    @api.model
    def _module_versions(self, names):
        """{name: {installed, code, pending}} of the modules ``names``: the
        version recorded in the database, the version of the manifest on
        disk as Odoo stores it, and whether they differ, the rule of the
        erplibre_info_git snapshots for an upgrade pending (-u). Read from
        the database and the manifests only."""
        records = {
            m.name: m
            for m in self.env["ir.module.module"]
            .sudo()
            .search([("name", "in", list(names))])
        }
        result = {}
        for name in names:
            record = records.get(name)
            installed = (record.latest_version if record else False) or False
            manifest = get_manifest(name) or {}
            code_version = safe_version(manifest.get("version")) or False
            result[name] = {
                "installed": installed,
                "code": code_version,
                "pending": bool(
                    installed and code_version and installed != code_version
                ),
            }
        return result

    @api.model
    def _server_actions_checks(self):
        """The three conditions of the erplibre_info server actions, each
        as a bool, and ``problem``: the message of the first one that
        fails (the odoo.conf flag names the configuration file the server
        read), or False."""
        Run = self.env["erplibre.code.run"]
        return {
            "flag": Run._flag_enabled(),
            "group": self.env.user.has_group("base.group_system"),
            "debug": Run._is_debug_mode(),
            "problem": Run._server_actions_problem(),
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
        erplibre_info or a ``repo_state.py`` entry (a dict). ``target`` is
        the commit the manifest branch resolves to; ``ahead`` and
        ``behind`` count the commits of HEAD not in it and the reverse,
        False when the target is unknown; ``alignment`` is the state of
        HEAD against it, before a modified tree turns ``state`` into
        ``sale``."""
        if labels is None:
            labels = self._repo_state_labels()
        get = line.get if isinstance(line, dict) else line.__getitem__
        state = get("state") or False
        alignment = get("alignment") or False
        target = get("target") or False

        def gap(key):
            # A clone without target has no gap: a snapshot line stores 0.
            value = get(key)
            return value if target and value is not None else False

        return {
            "path": get("path") or False,
            "state": state,
            "state_label": labels.get(state, state) if state else False,
            "branch": get("branch") or False,
            "head": get("head") or False,
            "dirty": bool(get("dirty")),
            "revision": get("revision") or False,
            "manifest_branch": get("manifest_branch") or False,
            "target": target,
            "ahead": gap("ahead"),
            "behind": gap("behind"),
            "alignment": alignment,
            "alignment_label": labels.get(alignment, alignment) if alignment else False,
            "error": get("error") or False,
        }

    @api.model
    def get_code_info(self, modules, refresh=False):
        """The code behind ``modules``: for each one its path, versions and
        the state of its git repository.

        The state comes from the last erplibre_info_git snapshot; a module
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

    @api.model
    def _repo_clone(self, repo, root):
        """The absolute path of the git clone ``repo``, a path relative to
        the checkout ``root`` or an absolute path. Raise unless it is the
        top of a clone that lies in the checkout, or the clone of a module
        of the addons path: the panel reads no other directory."""
        if not repo or not isinstance(repo, str):
            raise UserError(self.env._("No repository given."))
        root = os.path.realpath(root) if root else None
        if os.path.isabs(repo):
            real = os.path.realpath(repo)
        elif root:
            real = os.path.realpath(os.path.join(root, repo))
        else:
            real = False
        allowed = bool(real) and os.path.lexists(os.path.join(real, ".git"))
        if allowed and not (root and (real + os.sep).startswith(root + os.sep)):
            allowed = any(
                code.repository_of(os.path.realpath(path), root) == real
                for path in self._module_paths()
            )
        if not allowed:
            raise UserError(
                self.env._(
                    "%(repo)s is not a git repository of this server.", repo=repo
                )
            )
        return real

    @api.model
    def _module_paths(self):
        """The directories of the installed modules."""
        names = (
            self.env["ir.module.module"]
            .sudo()
            .search([("state", "=", "installed")])
            .mapped("name")
        )
        paths = (get_module_path(n, display_warning=False) for n in names)
        return [p for p in paths if p]

    @api.model
    def _snapshot_target(self, rel):
        """The manifest target of the repository ``rel`` in the last
        erplibre_info_git snapshot, or False."""
        snapshot = self.env["erplibre.code.snapshot"].search([], limit=1)
        line = snapshot.repo_ids.filtered(lambda r: r.path == rel)[:1]
        return line.target or False

    @api.model
    def get_repo_details(self, repo, target=False, limit=COMMIT_LIMIT):
        """What a repository holds beyond its state: its uncommitted
        changes and its recent commits.

        ``repo`` is the path of the clone relative to the checkout (the
        ``clone_rel`` of ``get_code_info``). ``target`` is the commit the
        manifest branch resolves to (``repo.target``); without it, the one
        of the last snapshot. Return {repo, dirty_count, dirty_files,
        commits, target, error}: ``dirty_files`` lists at most
        ``code.MAX_DIRTY_FILES`` of the ``dirty_count`` changed paths;
        ``commits`` holds the last ``limit`` commits of the clone, each
        with ``ahead`` True when the target does not contain it, False
        when it does, None when the target is unknown. A git failure is
        reported in ``error``, with what could be read."""
        self._check_panel_access()
        root = runner.erplibre_root(self.env)
        clone = self._repo_clone(repo, root)
        rel = code.relative_to(clone, root) if root else clone
        if not code.is_sha(target):
            target = self._snapshot_target(rel)
        result = {
            "repo": rel,
            "dirty_count": 0,
            "dirty_files": [],
            "commits": [],
            "target": target or False,
            "error": False,
        }
        errors = []
        try:
            result["dirty_count"], result["dirty_files"] = code.git_status(
                self.env, clone
            )
        except code.GitLogError as exc:
            errors.append(str(exc))
        try:
            commits = code.git_log(self.env, clone, ".", limit)
        except code.GitLogError as exc:
            errors.append(str(exc))
            commits = []
        ahead = None
        if commits and target:
            try:
                ahead = code.git_ahead(self.env, clone, target, len(commits))
            except code.GitLogError as exc:
                errors.append(str(exc))
        for commit in commits:
            commit["ahead"] = None if ahead is None else commit["sha"] in ahead
        result["commits"] = commits
        result["error"] = "\n".join(errors) or False
        return result

    # ── recent runs ─────────────────────────────────────────────────────

    @api.model
    def _run_modules(self, run, known):
        """The module names a run log lists after a colon, kept when they
        name a module of ``known``: erplibre_info writes the modules marked
        to upgrade in the log of a restart, as text."""
        names = []
        for line in (run.log or "").splitlines()[1:]:
            if ": " not in line:
                continue
            for name in line.rsplit(": ", 1)[1].split(","):
                name = name.strip()
                if name in known and name not in names:
                    names.append(name)
        return names

    @api.model
    def get_recent_runs(self, limit=RUN_LIMIT):
        """The last ``limit`` runs of erplibre_info (``erplibre.code.run``),
        most recent first: {id, run_type, type_label, state, state_label,
        user, date, date_start, date_end, modules}. The state is the one the
        run recorded: a restart is done when it is requested, the upgrade
        it asks for runs at the next start and is not followed here."""
        self._check_panel_access()
        limit = max(1, min(int(limit or RUN_LIMIT), RUN_LIMIT_MAX))
        Run = self.env["erplibre.code.run"]
        runs = Run.search([], limit=limit, order="id desc")
        types = dict(Run._fields["run_type"]._description_selection(self.env))
        states = dict(Run._fields["state"]._description_selection(self.env))
        known = (
            set(self.env["ir.module.module"].sudo().search([]).mapped("name"))
            if runs
            else set()
        )
        return [
            {
                "id": run.id,
                "run_type": run.run_type,
                "type_label": types.get(run.run_type, run.run_type),
                "state": run.state,
                "state_label": states.get(run.state, run.state),
                "user": run.user_id.name or False,
                "date": run.create_date or False,
                "date_start": run.date_start or False,
                "date_end": run.date_end or False,
                "modules": self._run_modules(run, known),
            }
            for run in runs
        ]

    # ── developer actions ───────────────────────────────────────────────

    @api.model
    def action_upgrade_modules(self, modules):
        """Open the erplibre_info confirmation (checkbox and database name
        typed again) that marks the modules named in ``modules`` to
        upgrade and restarts the server: the upgrade then runs at the next
        start, with the code on disk (see
        ``erplibre.code.run._request_restart``). Every name must be an
        installed module."""
        self._check_panel_access()
        self._check_server_actions()
        if isinstance(modules, str):
            modules = [modules]
        names = list(dict.fromkeys(n for n in modules or [] if n))
        if not names:
            raise UserError(self.env._("No module to upgrade."))
        records = (
            self.env["ir.module.module"]
            .sudo()
            .search([("name", "in", names), ("state", "=", "installed")])
        )
        found = set(records.mapped("name"))
        missing = [n for n in names if n not in found]
        if missing:
            raise UserError(
                self.env._(
                    "Module %(module)s is not installed.", module=", ".join(missing)
                )
            )
        return self.env["erplibre.code.confirm.wizard"]._action_open(
            "restart_upgrade", modules=records
        )

    @api.model
    def action_upgrade_module(self, module):
        """``action_upgrade_modules`` for the one module ``module``."""
        return self.action_upgrade_modules([module])

    @api.model
    def action_reload_assets(self):
        """Delete the generated asset bundles: the next page load builds
        them from the files on disk."""
        self._check_panel_access()
        self.env["ir.attachment"].sudo().regenerate_assets_bundles()
        return True
