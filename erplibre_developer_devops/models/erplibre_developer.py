# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import re

from odoo import api, models
from odoo.exceptions import UserError

# The characters of a path that both shells of erplibre_devops read as
# plain text: the PyCharm command line, then its single-quoted
# « bash -c '…' » wrapper in a terminal. No quote, no space, no shell
# metacharacter.
_SHELL_SAFE_PATH = re.compile(r"[A-Za-z0-9._/+-]+")


class ErplibreDeveloper(models.AbstractModel):
    """The IDE opener of the developer panel: the PyCharm of the DevOps
    workspace that manages this server (« is_me »)."""

    _inherit = "erplibre.developer"

    @api.model
    def _ide_workspace(self):
        return self.env["devops.workspace"].search(
            [("is_me", "=", True), ("ide_pycharm", "!=", False)], limit=1
        )

    @api.model
    def _ide_available(self):
        return bool(self._ide_workspace()) or super()._ide_available()

    @api.model
    def _ide_open(self, path, line):
        """Open ``path`` at ``line`` with
        ``devops.ide.pycharm.action_pycharm_open``. That method builds a
        shell line that erplibre_devops wraps in a single-quoted
        ``bash -c '…'``: no quoting survives both shells, so a path outside
        ``_SHELL_SAFE_PATH`` is refused with its ``path:line`` to open by
        hand. The line is an integer."""
        workspace = self._ide_workspace()
        if not workspace:
            return super()._ide_open(path, line)
        line = int(line or 0)
        if not _SHELL_SAFE_PATH.fullmatch(path or ""):
            location = f"{path}:{line}" if line > 0 else path
            raise UserError(
                self.env._(
                    "This path cannot be passed to the IDE command line; "
                    "open it by hand: %(location)s",
                    location=location,
                )
            )
        with workspace.devops_create_exec_bundle("Open in PyCharm") as rec_ws:
            rec_ws.ide_pycharm.action_pycharm_open(
                rec_ws,
                filename=path,
                pycharm_arg=f"--line {line}" if line > 0 else None,
            )
        return True
