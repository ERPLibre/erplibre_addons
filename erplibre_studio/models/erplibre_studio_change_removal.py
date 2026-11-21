# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, models
from odoo.exceptions import UserError

from .erplibre_studio_review import _Review


class ErplibreStudioEditor(models.AbstractModel):
    """Undo one change of the draft, whatever its place: what leaves with
    it, then its removal once the user confirmed that list."""

    _inherit = "erplibre.studio.editor"

    @api.model
    def _draft_change(self, project, change_id):
        """The change ``change_id`` of ``project``; UserError when the draft
        of the project does not hold it."""
        change = project.change_ids.filtered(lambda c: c.id == int(change_id or 0))
        if not change:
            raise UserError(
                self.env._("This change is not in the draft of the project.")
            )
        return change

    @api.model
    def get_change_removal(self, project_id, change_id):
        """What undoing the change ``change_id`` of the project
        ``project_id`` removes (``_studio_change_removal``): {revision,
        change, items, refused, applied}. ``change`` and each of ``items``
        (the other changes that leave, in the order they apply): {id,
        summary, view, view_type, applied}, ``applied`` when the last Apply
        wrote it as it is. ``refused``: why the undo is refused, or False.
        ``applied``: whether one of them is applied. A read."""
        self._check_studio_access()
        project = self._read_project(project_id)
        change = self._draft_change(project, change_id)
        closure = project._studio_change_removal(change)
        try:
            project._studio_check_inverse_removal(closure)
            refused = False
        except UserError as exc:
            refused = exc.args[0]
        review = _Review(self, project)

        def item(record):
            return {
                "id": record.id,
                "summary": record.summary,
                "view": record._studio_view_label(),
                "view_type": record.view_type,
                "applied": review.is_applied("changes", record),
            }

        items = [item(record) for record in closure]
        return {
            "revision": project.draft_revision,
            "change": item(change),
            "items": [value for value in items if value["id"] != change.id],
            "refused": refused,
            "applied": any(value["applied"] for value in items),
        }

    @api.model
    def remove_change(
        self,
        project_id,
        change_id,
        expected,
        model,
        view_id,
        view_type,
        revision=None,
    ):
        """Remove the change ``change_id`` from the draft with what leaves
        with it (``_studio_remove_changes``); the payload of the view on
        screen, with ``removed``, the ids of the removed changes.
        ``expected``: the ids ``get_change_removal`` listed, the change
        with its items; UserError when the removal no longer matches them.
        None skips that check. ``revision``: see ``_edited_project``."""
        self._check_studio_access()
        project = self._edited_project(project_id, revision)
        view = self._resolve_view(model, view_id, view_type, project)
        change = self._draft_change(project, change_id)
        if expected is not None:
            closure = project._studio_change_removal(change)
            if {int(i) for i in expected} != set(closure.ids):
                raise UserError(
                    self.env._(
                        "What this undo removes changed since you confirmed "
                        "it: check it again."
                    )
                )
        removed = project._studio_remove_changes(change)
        return self._answer(project, model, view.id, view_type, removed=removed)
