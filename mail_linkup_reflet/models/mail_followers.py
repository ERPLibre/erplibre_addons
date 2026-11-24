# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import models
from odoo.osv import expression

from . import privacy

# The contact details a follower carries from its partner.
FOLLOWER_CONTACT_FIELDS = frozenset({"email"})


class MailFollowers(models.Model):
    """The address of a follower, closed to a restricted member as that of
    its partner (LU-NF-009, LU-F-112 RM3).

    ``email`` is related to the partner and read under ``sudo``, as Odoo
    reads a related field: the follower list of a document, read or sent
    in the Discuss Store, would otherwise carry the address of each
    follower, and a search on it would match the hidden address of any
    of them.
    """

    _inherit = ["mail.followers", "linkup.contact.privacy"]
    _name = "mail.followers"

    _linkup_contact_fields = FOLLOWER_CONTACT_FIELDS

    def _linkup_contact_own(self):
        own = self.env.user.partner_id
        # sudo: mail.followers - the partner of the followers read
        return self.filtered(
            lambda follower: follower.sudo().partner_id == own
        )

    def _read_format(self, fnames, load="_classic_read"):
        """Blank the address of the followers in what a restricted member
        reads, but their own; the Discuss Store reads them here."""
        result = super()._read_format(fnames, load)
        closed = FOLLOWER_CONTACT_FIELDS.intersection(fnames)
        if closed and privacy.contact_closed(self.env):
            own = set(self._linkup_contact_own().ids)
            for vals in result:
                if vals.get("id") in own:
                    continue
                for fname in closed:
                    if fname in vals:
                        vals[fname] = False
        return result

    def _search(self, domain, offset=0, limit=None, order=None):
        """A condition of a restricted member on the address of a follower
        matches nothing: Odoo resolves it on the partners under ``sudo``,
        where ``res.partner._condition_to_sql`` lets it through."""
        domain = [
            (
                expression.FALSE_LEAF
                if expression.is_leaf(leaf)
                and isinstance(leaf[0], str)
                and privacy.search_closed(
                    self, leaf[0].split(".", 1)[0], FOLLOWER_CONTACT_FIELDS
                )
                else leaf
            )
            for leaf in domain
        ]
        return super()._search(domain, offset=offset, limit=limit, order=order)
