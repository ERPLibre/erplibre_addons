# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import _, fields, models
from odoo.addons.mail.tools.discuss import Store
from odoo.exceptions import AccessError
from odoo.tools import SQL

from . import privacy

# Fields of a message that hold the address of its author: Odoo writes
# ``email_from`` and ``reply_to`` from the address of the partner who posts.
AUTHOR_CONTACT_FIELDS = frozenset({"email_from", "reply_to"})


class MailMessage(models.Model):
    _inherit = "mail.message"

    # Set by the moderation, which moves the body and the attachments of the
    # message to ``linkup.hidden.content`` (LU-F-116 RM2).
    linkup_hidden = fields.Boolean(
        string="Hidden by the moderation", readonly=True, copy=False
    )

    def write(self, vals):
        """Keep the mark of the moderation to the server: the author of a
        message may otherwise write it on their own message."""
        if "linkup_hidden" in vals and not self.env.su:
            raise AccessError(
                _("Only the moderation hides a message or shows it again.")
            )
        return super().write(vals)

    def _to_store(self, store: Store, /, *, fields=None, **kwargs):
        """Mark a hidden message, which every client then draws as
        "Message hidden by the moderation". Its body is already empty; the
        key is sent for a hidden message only, the client reading its
        absence as visible."""
        super()._to_store(store, fields=fields, **kwargs)
        for message in self.filtered("linkup_hidden"):
            store.add(message, {"linkup_hidden": True})

    def _author_to_store(self, store: Store):
        """Leave out of the Store the address of the author of a message,
        as ``res.partner._to_store`` leaves it out of the partner: for
        every message a restricted member reads, and for the messages of a
        restricted member whoever reads. A client draws the author of a
        message from its partner."""
        super()._author_to_store(store)
        closed = privacy.contact_closed(self.env)
        members = {}
        for message in self:
            author = message.sudo().author_id
            if author and author.id not in members:
                members[author.id] = author._linkup_is_member_partner()
            if closed or members.get(author.id):
                store.add(message, {"email_from": False})

    def _read_format(self, fnames, load="_classic_read"):
        """Blank the address of the author in the messages a restricted
        member reads, but in their own messages."""
        result = super()._read_format(fnames, load)
        closed = AUTHOR_CONTACT_FIELDS.intersection(fnames)
        if closed and privacy.contact_closed(self.env):
            own = self.env.user.partner_id.id
            authors = {
                message.id: message.author_id.id for message in self.sudo()
            }
            for vals in result:
                if authors.get(vals.get("id")) == own:
                    continue
                for fname in closed:
                    if fname in vals:
                        vals[fname] = False
        return result

    def _condition_to_sql(self, alias, fname, operator, value, query):
        """A restricted member searches no message by the address of its
        author."""
        if privacy.search_closed(self, fname, AUTHOR_CONTACT_FIELDS):
            return SQL("FALSE")
        return super()._condition_to_sql(alias, fname, operator, value, query)
