# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

from odoo import api, models
from odoo.exceptions import UserError

from .. import arch as studio_arch
from .erplibre_studio_review import _Review
from .studio_pending import is_pending_view

_logger = logging.getLogger(__name__)


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
    def _removal_model_name(self, view):
        """The name of the model of ``view`` for a reader: the one of its
        model line for a model the project has not created yet, else the
        one of ir.model."""
        if is_pending_view(view):
            return view.line.name or view.model
        return self.env["ir.model"]._get(view.model).name or view.model

    @api.model
    def _removal_subjects(self, project, changes):
        """{change id: ``arch.change_subject``} of ``changes`` of
        ``project``, read in the draft arch of each of their views
        (``_subject_observer``). A view whose draft cannot be read gives
        no subject: the editor then shows the summary of its changes."""
        subjects = {}
        views = {}
        for change in changes:
            key = (
                change.view_id.id,
                change.view_line_id.id,
                change.model_line_id.id,
                change.view_type,
            )
            views.setdefault(key, change)
        for change in views.values():
            view = project._change_view(change)
            try:
                fields_info = self._fields_payload(view.model, project)
                observe = self._subject_observer(subjects, view.type, fields_info)
                project._draft_arch(view, observe=observe)
            except Exception:  # noqa: BLE001 - a sentence never blocks the undo
                _logger.debug("No subject for the changes of %s", view.name)
        found = set(changes.ids)
        return {key: value for key, value in subjects.items() if key in found}

    @api.model
    def get_change_removal(self, project_id, change_id):
        """What undoing the change ``change_id`` of the project
        ``project_id`` removes (``_studio_change_removal``): {revision,
        change, items, refused, applied}. ``change`` and each of ``items``
        (the other changes that leave, in the order they apply): {id,
        summary, view, view_type, model_name, type, kind, attribute,
        subject, applied}, ``applied`` when the last Apply wrote it as it
        is; ``type`` to ``subject`` as ``get_editor_data`` lists a change,
        from which the editor builds its plain sentence, and
        ``model_name`` the name of its model for a reader. ``refused``: why
        the undo is refused, or False. ``applied``: whether one of them is
        applied. A read."""
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
        subjects = self._removal_subjects(project, closure)
        names = {}

        def item(record):
            spec = record._as_dict()
            if record.model not in names:
                view = project._change_view(record)
                names[record.model] = self._removal_model_name(view)
            return {
                "id": record.id,
                "summary": record.summary,
                "view": record._studio_view_label(),
                "view_type": record.view_type,
                "model_name": names[record.model],
                "type": record.change_type,
                "kind": studio_arch.change_kind(spec),
                "attribute": (
                    record.change_type == "set_attribute"
                    and spec["payload"].get("attribute")
                )
                or False,
                "subject": subjects.get(record.id) or False,
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
