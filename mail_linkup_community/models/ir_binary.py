# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import models

from . import privacy


class IrBinary(models.AbstractModel):
    _inherit = "ir.binary"

    def _record_to_stream(self, record, field_name):
        """Serve the placeholder instead of the photo of a member who is
        neither the reader nor linked to them, when the reader is a
        restricted member (Q-27): ``/web/image``, ``/web/content`` and the
        avatars of Discuss go through here, also with an access token."""
        partner = self._linkup_photo_partner(record, field_name)
        if partner and privacy.closed_photo_partner_ids(self.env, partner.ids):
            return self._get_placeholder_stream(
                partner._avatar_get_placeholder_path()
            )
        return super()._record_to_stream(record, field_name)

    def _linkup_photo_partner(self, record, field_name):
        """The partner whose photo ``field_name`` of ``record`` holds,
        under ``sudo``, or ``None``: a photo of a partner or of a user, the
        avatar of the author of a message, and the attachment that stores
        the photo of a partner or of a user."""
        if not privacy.contact_closed(self.env):
            return None
        record.ensure_one()
        # sudo: the owner of the photo, read to choose what is served
        record = record.sudo()
        if record._name == "mail.message":
            return record.author_id if field_name == "author_avatar" else None
        if record._name == "ir.attachment":
            owner_model, field_name = record.res_model, record.res_field
            if owner_model not in privacy.PHOTO_MODELS:
                return None
            record = self.env[owner_model].sudo().browse(record.res_id)
        if (
            record._name not in privacy.PHOTO_MODELS
            or field_name not in privacy.IMAGE_FIELDS
        ):
            return None
        record = record.exists()
        if record._name == "res.users":
            return record.partner_id
        return record
