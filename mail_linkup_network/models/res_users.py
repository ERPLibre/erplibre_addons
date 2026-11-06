# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import _, api, fields, models
from odoo.addons.mail.tools.discuss import Store
from odoo.addons.mail_linkup_reflet.models.res_users import (
    ADMIN_GROUP,
    MEMBER_GROUP,
)
from odoo.exceptions import AccessError

# Preferences of the network that a member reads and writes on their own
# account (LU-F-082 RM4), off by default (LU-NF-012).
NETWORK_PREFERENCES = ("linkup_links_visible", "linkup_energy_visible")
# Fields of the gamification that tell the activity of a user: their karma
# with its penalties, the rank it gives, and their badges. A restricted
# member reads them on their own account only; the energy of a linked
# member who shows it reaches them rounded, through ``get_ranking``.
GAMIFICATION_FIELDS = frozenset(
    {
        "karma",
        "karma_tracking_ids",
        "rank_id",
        "next_rank_id",
        "badge_ids",
        "gold_badge",
        "silver_badge",
        "bronze_badge",
    }
)


def blank_value(field):
    """The value a reading gives for a field it keeps closed."""
    return [] if field.type in ("one2many", "many2many") else False


class ResUsers(models.Model):
    _inherit = "res.users"

    # Kept to the LinkUp administrators: a member reads and writes their
    # own through ``SELF_READABLE_FIELDS`` and ``SELF_WRITEABLE_FIELDS``,
    # and the server reads those of the others under ``sudo``.
    linkup_links_visible = fields.Boolean(
        string="My links are visible to my links",
        default=False,
        copy=False,
        groups=ADMIN_GROUP,
        help="The Network view of a linked member draws a grey line"
        " between you and another of their contacts who shows their links"
        " too.",
    )
    linkup_energy_visible = fields.Boolean(
        string="My energy is visible to my links",
        default=False,
        copy=False,
        groups=ADMIN_GROUP,
        help="Your linked members see your energy, rounded and without"
        " penalties, in their ranking of the most active.",
    )

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + list(NETWORK_PREFERENCES)

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + list(NETWORK_PREFERENCES)

    def write(self, vals):
        """Send the new network preferences to the web clients of the
        member, so that every open tab shows them."""
        res = super().write(vals)
        if any(key in vals for key in NETWORK_PREFERENCES):
            for user in self.sudo():
                user.partner_id._bus_send_store(
                    {key: user[key] for key in NETWORK_PREFERENCES}
                )
        return res

    def _init_store_data(self, store: Store, /):
        """Give a member their network preferences and the number of
        partners the strongest density keeps."""
        super()._init_store_data(store)
        user = self.env.user
        if user._is_public() or not user._linkup_has_group_id(MEMBER_GROUP):
            return
        me = user.sudo()
        values = {key: me[key] for key in NETWORK_PREFERENCES}
        values["linkup_network_top_count"] = self.env[
            "linkup.link"
        ]._linkup_network_top_count()
        store.add(values)

    # ------------------------------------------------------------------
    # Gamification of the other users (LU-NF-012, LU-F-073 RM2)
    # ------------------------------------------------------------------

    def _linkup_gamification_closed(self):
        """Whether the current user reads the gamification of their own
        account only: a restricted member, outside ``sudo``, who is not a
        LinkUp administrator."""
        if self.env.su:
            return False
        user = self.env.user
        return user._linkup_is_restricted_member() and not (
            user._linkup_has_group_id(ADMIN_GROUP)
        )

    def _linkup_gamification_refused(self, fname):
        """Refuse a search, an order or a grouping on a field of
        ``GAMIFICATION_FIELDS`` to a member whose reading is closed: each
        one would sort or count the other users by their activity."""
        if (
            fname.split(".", 1)[0] in GAMIFICATION_FIELDS
            and self._linkup_gamification_closed()
        ):
            raise AccessError(
                _("The points, rank and badges of a member are theirs alone.")
            )

    def _read_format(self, fnames, load="_classic_read"):
        """Leave out the gamification of the other users from what a
        restricted member reads: ``read``, ``web_read`` and ``search_read``
        give them an empty value. The values are blanked after the
        reading, so the cache keeps the true ones for the server."""
        result = super()._read_format(fnames, load)
        closed = GAMIFICATION_FIELDS.intersection(fnames)
        if closed and self._linkup_gamification_closed():
            uid = self.env.uid
            for vals in result:
                if vals.get("id") == uid:
                    continue
                for fname in closed:
                    if fname in vals:
                        vals[fname] = blank_value(self._fields[fname])
        return result

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None):
        """Refuse a domain on the gamification, its paths included
        (``rank_id.name``, ``badge_ids.badge_id``): the expression turns
        a path into a subquery that ``_condition_to_sql`` does not see."""
        for leaf in domain or ():
            if (
                isinstance(leaf, (list, tuple))
                and len(leaf) == 3
                and isinstance(leaf[0], str)
            ):
                self._linkup_gamification_refused(leaf[0])
        return super()._search(domain, offset=offset, limit=limit, order=order)

    def _condition_to_sql(self, alias, fname, operator, value, query):
        self._linkup_gamification_refused(fname)
        return super()._condition_to_sql(alias, fname, operator, value, query)

    def _order_field_to_sql(self, alias, field_name, direction, nulls, query):
        self._linkup_gamification_refused(field_name)
        return super()._order_field_to_sql(
            alias, field_name, direction, nulls, query
        )

    @api.model
    def _read_group_groupby(self, groupby_spec, query):
        self._linkup_gamification_refused(groupby_spec.split(":", 1)[0])
        return super()._read_group_groupby(groupby_spec, query)

    @api.model
    def _read_group_select(self, aggregate_spec, query):
        self._linkup_gamification_refused(aggregate_spec.split(":", 1)[0])
        return super()._read_group_select(aggregate_spec, query)
