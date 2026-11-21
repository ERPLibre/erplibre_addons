# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, models

from .erplibre_studio_project import EXCLUDE_KEY, PREVIEW_KEY, ViewExclusion


class Base(models.AbstractModel):
    """The draft preview of a studio project in get_views: for the editor
    of the project only, when the context names it. A view the project adds
    shows in place of the default Odoo builds for a type without view."""

    _inherit = "base"

    @api.model
    def _get_view_cache_key(self, view_id=None, view_type="form", **options):
        """The context value is already in the key (a « *_view_ref » key);
        the user is added: the draft is computed for its editor only."""
        key = super()._get_view_cache_key(view_id, view_type, **options)
        if self.env.context.get(PREVIEW_KEY):
            key += ((PREVIEW_KEY, self.env.uid),)
        excluded = self.env.context.get(EXCLUDE_KEY)
        if isinstance(excluded, ViewExclusion) and excluded:
            # An arch without some views never takes the shared entry.
            key += ((EXCLUDE_KEY, tuple(sorted(excluded))),)
        return key

    @api.model
    def _get_view(self, view_id=None, view_type="form", **options):
        project = self.env["erplibre.studio.project"]._preview_project()
        if not project:
            return super()._get_view(view_id, view_type, **options)
        added = None if view_id else project._studio_added_view(self._name, view_type)
        if added:
            # The view the project adds, before Apply creates it, with its
            # draft: in place of the default Odoo builds for a type without
            # view, which a type such as « timeline » does not have.
            arch = project._preview_arch(project._base_arch(added), added, self._name)
            return arch, self.env["ir.ui.view"]
        excluded = {EXCLUDE_KEY: ViewExclusion(project.studio_view_ids.ids)}
        arch, view = super(Base, self.with_context(**excluded))._get_view(
            view_id, view_type, **options
        )
        if view:
            arch = project._preview_arch(arch, view, self._name)
        return arch, view
