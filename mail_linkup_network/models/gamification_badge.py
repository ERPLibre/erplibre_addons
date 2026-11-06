# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import models

from .res_users import blank_value

# Fields of a badge that tell who else holds it: the native computation
# counts and lists its holders within the scope of the reader, that is
# among the linked members and the members of a shared conversation.
OWNER_FIELDS = ("unique_owner_ids", "granted_count", "granted_users_count")


class GamificationBadge(models.Model):
    _inherit = "gamification.badge"

    def _read_format(self, fnames, load="_classic_read"):
        """Give a restricted member the holders of a badge among
        themself only, and no count of the others (LU-NF-012)."""
        result = super()._read_format(fnames, load)
        closed = [fname for fname in OWNER_FIELDS if fname in fnames]
        if closed and self.env["res.users"]._linkup_gamification_closed():
            uid = self.env.uid
            for vals in result:
                for fname in closed:
                    if fname not in vals:
                        continue
                    if fname == "unique_owner_ids":
                        vals[fname] = [
                            user_id
                            for user_id in vals[fname]
                            if user_id == uid
                        ]
                    else:
                        vals[fname] = blank_value(self._fields[fname])
        return result
