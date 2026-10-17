# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, models

from .erplibre_studio_project import EXCLUDE_KEY, PREVIEW_KEY, ViewExclusion


class Base(models.AbstractModel):
    """The draft preview of a studio project in get_views: for the editor
    of the project only, when the context names it."""

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
        excluded = {EXCLUDE_KEY: ViewExclusion(project.studio_view_ids.ids)}
        arch, view = super(Base, self.with_context(**excluded))._get_view(
            view_id, view_type, **options
        )
        if view:
            arch = project._preview_arch(arch, view, self._name)
        return arch, view
