# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import re

from odoo import fields, models
from odoo.tools import parse_version

_SHA = re.compile(r"^[0-9a-f]{40}$")

# The states of a snapshot repository without a commit to return to.
STATES_WITHOUT_HEAD = ("absent", "erreur")


class ErplibreCodeSnapshot(models.Model):
    _inherit = "erplibre.code.snapshot"

    git_fetch_allowed = fields.Boolean(compute="_compute_git_fetch_allowed")

    def _compute_git_fetch_allowed(self):
        allowed = self.env["erplibre.code.run"]._git_fetch_allowed()
        for snap in self:
            snap.git_fetch_allowed = allowed

    def _revert_targets(self, include_root=True):
        """The targets file of a return to this snapshot, as
        ``repo_pull.py --targets`` reads it: ``{"racine": {head, branch} |
        None, "depots": {path: {head, branch, remote}}}``. A repository
        whose snapshot line has no full commit (missing, unreadable) is
        left out, as is the root without ``include_root``."""
        self.ensure_one()
        root = None
        if include_root and _SHA.match(self.erplibre_head or ""):
            root = {
                "head": self.erplibre_head,
                "branch": self.erplibre_branch or None,
            }
        repos = {}
        for line in self.repo_ids.sorted("path"):
            if (
                line.path in ("", ".")
                or line.state in STATES_WITHOUT_HEAD
                or not _SHA.match(line.head or "")
            ):
                continue
            repos[line.path] = {
                "head": line.head,
                "branch": line.branch or None,
                "remote": line.remote or None,
            }
        return {"racine": root, "depots": repos}

    def _revert_newer_modules(self):
        """The installed modules that a return to this snapshot would run
        on older code: those whose version in the database is newer than
        the one the snapshot recorded, and those the snapshot did not have
        installed. A snapshot without module lines lists none. Return
        ``[{name, snapshot_version, installed_version}]`` sorted by name."""
        self.ensure_one()
        if not self.module_ids:
            return []
        recorded = {m.name: m.installed_version for m in self.module_ids}
        newer = []
        for module in self._installed_modules():
            installed = module.latest_version or ""
            before = recorded.get(module.name)
            if module.name in recorded and not (
                installed
                and before
                and parse_version(installed) > parse_version(before)
            ):
                continue
            newer.append(
                {
                    "name": module.name,
                    "snapshot_version": before or False,
                    "installed_version": installed,
                }
            )
        return newer

    def action_revert(self):
        """Open the wizard of the return to this snapshot."""
        self.ensure_one()
        return self.env["erplibre.code.revert.wizard"]._action_open(self)
