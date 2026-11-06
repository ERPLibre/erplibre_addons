# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import _, api, models
from odoo.exceptions import AccessError

# Field of a rank that tells who holds it; ``rank_users_count`` is
# neither stored nor searchable.
HOLDER_FIELD = "user_ids"


class GamificationKarmaRank(models.Model):
    _inherit = "gamification.karma.rank"

    def _linkup_holders_refused(self, fname):
        """Refuse a search on the holders of a rank to a
        member whose reading of the gamification is closed: a search of
        the ranks held by a user tells the rank of that user."""
        if (
            fname.split(".", 1)[0] == HOLDER_FIELD
            and self.env["res.users"]._linkup_gamification_closed()
        ):
            raise AccessError(
                _("The points, rank and badges of a member are theirs alone.")
            )

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None):
        """Refuse a domain on the holders, paths included: a one2many
        condition turns into a subquery on ``res_users`` that the users
        model does not see."""
        for leaf in domain or ():
            if (
                isinstance(leaf, (list, tuple))
                and len(leaf) == 3
                and isinstance(leaf[0], str)
            ):
                self._linkup_holders_refused(leaf[0])
        return super()._search(domain, offset=offset, limit=limit, order=order)

    def _condition_to_sql(self, alias, fname, operator, value, query):
        self._linkup_holders_refused(fname)
        return super()._condition_to_sql(alias, fname, operator, value, query)
