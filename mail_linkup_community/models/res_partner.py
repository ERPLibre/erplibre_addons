# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import models

from . import privacy


class ResPartner(models.Model):
    _inherit = "res.partner"

    def _read_format(self, fnames, load="_classic_read"):
        """Blank the photo of the partners not linked to a restricted
        member in what they read; ``mail_linkup_reflet`` blanks the contact
        details."""
        result = super()._read_format(fnames, load)
        if privacy.contact_closed(self.env):

            def linked():
                users = (
                    self.env["res.users"]
                    .sudo()
                    .browse(privacy.linked_user_ids(self.env))
                )
                return set(users.partner_id.ids)

            privacy.mask_images(
                self, result, fnames, self.env.user.partner_id.id, linked
            )
        return result

    def _linkup_export_masks(self, fields):
        """Blank in an export the photo of the partners not linked to a
        restricted member."""
        masks = super()._linkup_export_masks(fields)
        mask = privacy.export_photo_mask(
            self, fields, privacy.IMAGE_FIELDS, lambda partner: partner
        )
        return masks + [mask] if mask else masks
