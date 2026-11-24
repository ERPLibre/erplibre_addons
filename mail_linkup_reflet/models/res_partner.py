# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import api, models
from odoo.addons.mail.tools.discuss import Store
from odoo.tools import SQL

from . import privacy

# Keys of the context that add the contact details of a partner to its
# display name.
DISPLAY_CONTACT_KEYS = ("show_email", "show_address", "show_vat")


class ResPartner(models.Model):
    _inherit = ["res.partner", "linkup.contact.privacy"]
    _name = "res.partner"

    _linkup_contact_fields = privacy.CONTACT_FIELDS

    def _linkup_contact_own(self):
        return self & self.env.user.partner_id

    def _read_format(self, fnames, load="_classic_read"):
        """Blank the contact details of the other partners in what a
        restricted member reads."""
        result = super()._read_format(fnames, load)
        if privacy.contact_closed(self.env):
            privacy.mask_contact_rows(
                self,
                result,
                fnames,
                privacy.CONTACT_FIELDS,
                self.env.user.partner_id.id,
            )
        return result

    @api.depends_context("uid")
    def _compute_display_name(self):
        """Keep the address, the postal address and the tax number of the
        other partners out of the display name a restricted member reads,
        whatever the context asks for: ``show_email`` would otherwise
        write the address after the name. The name then depends on the
        reader too."""
        super()._compute_display_name()
        context = self.env.context
        if not any(context.get(key) for key in DISPLAY_CONTACT_KEYS):
            return
        if not privacy.contact_closed(self.env):
            return
        others = self - self.env.user.partner_id
        plain = others.with_context(
            **dict.fromkeys(DISPLAY_CONTACT_KEYS, False)
        )
        super(ResPartner, plain)._compute_display_name()
        for partner, plain_partner in zip(others, plain):
            partner.display_name = plain_partner.display_name

    def _condition_to_sql(self, alias, fname, operator, value, query):
        """A restricted member searches no partner by its contact details:
        ``name_search``, ``im_search``, the mention suggestions and the
        invitation search of Discuss then match on the name only
        (LU-F-112 RM3)."""
        if privacy.search_closed(self, fname, privacy.CONTACT_FIELDS):
            return SQL("FALSE")
        return super()._condition_to_sql(alias, fname, operator, value, query)

    def _track_filter_for_display(self, tracking_values):
        """Leave out of the history of another partner, as a restricted
        member reads it, the changes of its contact details: each one holds
        the former value and the new one. A change of the address of a
        member, in their preferences or their profile, writes their
        partner, which ``mail`` tracks."""
        tracking_values = super()._track_filter_for_display(tracking_values)
        if self == self.env.user.partner_id or not privacy.contact_closed(
            self.env
        ):
            return tracking_values
        return tracking_values.filtered(
            lambda tracking: tracking.sudo().field_id.name
            not in privacy.TRACKED_CONTACT_FIELDS
        )

    def _to_store(self, store: Store, /, **kwargs):
        """Leave the address out of the Discuss Store: for every partner
        when a restricted member reads, and for the partner of a restricted
        member whoever reads. A post of a member sends their own partner to
        the whole conversation, read as themself."""
        super()._to_store(store, **kwargs)
        partners = store.data.get("res.partner")
        if not partners:
            return
        closed = privacy.contact_closed(self.env)
        for partner in self:
            vals = partners.get((partner.id,))
            if not vals or "email" not in vals:
                continue
            if closed or partner.sudo()._linkup_is_member_partner():
                vals.pop("email")

    def _linkup_is_member_partner(self):
        """Whether the partner belongs to a restricted LinkUp member."""
        self.ensure_one()
        return any(
            user._linkup_is_restricted_member()
            for user in self.sudo().with_context(active_test=False).user_ids
        )

    def _linkup_outsider_partners(self):
        """The partners among these ones that no internal user holds, an
        archived account included: the partner of a portal user, or a
        contact without a user."""
        return self.filtered(
            lambda partner: not any(
                not user.share
                for user in partner.sudo()
                .with_context(active_test=False)
                .user_ids
            )
        )

    def _linkup_plain_member_partners(self):
        """The partners of a plain member among these ones, an archived
        account included (``res.users._linkup_is_plain_member``)."""
        return self.filtered(
            lambda partner: any(
                user._linkup_is_plain_member()
                for user in partner.sudo()
                .with_context(active_test=False)
                .user_ids
            )
        )
