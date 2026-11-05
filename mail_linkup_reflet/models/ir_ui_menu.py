# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import api, models, tools


class IrUiMenu(models.Model):
    _inherit = "ir.ui.menu"

    @api.model
    @tools.ormcache("frozenset(self.env.user.groups_id.ids)", "debug")
    def _visible_menu_ids(self, debug=False):
        """Keep only the Discuss tree for a LinkUp member.

        A member who is not a system administrator sees no root menu other
        than Discuss, whatever the installed modules grant to
        ``base.group_user``. Filtering here, rather than in
        ``_load_menus_blacklist``, also removes the root menus from the app
        switcher: the blacklist only applies to the descendants of the
        roots. The result depends on the user's groups only, which is the
        key of the cache.
        """
        visible_ids = super()._visible_menu_ids(debug=debug)
        if not self.env.user._linkup_is_restricted_member():
            return visible_ids
        discuss_root = self.env.ref(
            "mail.menu_root_discuss", raise_if_not_found=False
        )
        if not discuss_root:
            return set()
        prefix = f"{discuss_root.id}/"
        menus = (
            self.sudo()
            .with_context(**{"ir.ui.menu.full_list": True})
            .browse(visible_ids)
        )
        return {
            menu.id for menu in menus if menu.parent_path.startswith(prefix)
        }
