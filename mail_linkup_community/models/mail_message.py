# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import _, fields, models
from odoo.addons.mail.tools.discuss import Store
from odoo.exceptions import AccessError

from . import privacy

# The avatar of the author that a message reads from its partner.
AUTHOR_PHOTO_FIELDS = frozenset({"author_avatar"})


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

    def _read_format(self, fnames, load="_classic_read"):
        """Blank the avatar of the author of a message, as a restricted
        member reads it, when the photo of the author is closed to them
        (Q-27): ``author_avatar`` reads it from the partner under
        ``sudo``."""
        result = super()._read_format(fnames, load)
        if "author_avatar" not in fnames or not privacy.contact_closed(
            self.env
        ):
            return result
        # sudo: mail.message - the author of the messages read
        authors = {message.id: message.sudo().author_id.id for message in self}
        closed = privacy.closed_photo_partner_ids(self.env, authors.values())
        for vals in result:
            if (
                authors.get(vals.get("id")) in closed
                and "author_avatar" in vals
            ):
                vals["author_avatar"] = False
        return result

    def _linkup_export_masks(self, fields):
        """Blank in an export the avatar of the authors not linked to a
        restricted member."""
        masks = super()._linkup_export_masks(fields)
        mask = privacy.export_photo_mask(
            self,
            fields,
            AUTHOR_PHOTO_FIELDS,
            lambda message: message.author_id,
        )
        return masks + [mask] if mask else masks

    def _to_store(self, store: Store, /, *, fields=None, **kwargs):
        """Mark a hidden message, which every client then draws as
        "Message hidden by the moderation". Its body is already empty; the
        key is sent for a hidden message only, the client reading its
        absence as visible."""
        super()._to_store(store, fields=fields, **kwargs)
        for message in self.filtered("linkup_hidden"):
            store.add(message, {"linkup_hidden": True})
