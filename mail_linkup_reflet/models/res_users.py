# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import _, api, fields, models
from odoo.addons.auth_signup.models.res_partner import SignupError
from odoo.addons.base.models.res_users import is_reified_group
from odoo.addons.mail.tools.discuss import Store
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import email_normalize

from ..exceptions import LinkupError

MEMBER_GROUP = "mail_linkup_reflet.group_linkup_member"
ADMIN_GROUP = "mail_linkup_reflet.group_linkup_admin"
# Global switch of the first-use tour (LU-F-083), "True" unless set to
# "False": an unset parameter keeps the tour on.
FIRST_USE_TOUR_PARAM = "linkup.first_use_tour"
# Inactive user copied for a signup through an invitation (LU-F-020 RM2).
MEMBER_TEMPLATE_XMLID = "mail_linkup_reflet.user_linkup_member_template"


class ResUsers(models.Model):
    _inherit = "res.users"

    # Both sides of the LinkUp links of the user; the record rules of
    # security/linkup_rules.xml walk them to open the linked members.
    linkup_link_a_ids = fields.One2many("linkup.link", "user_a_id")
    linkup_link_b_ids = fields.One2many("linkup.link", "user_b_id")
    linkup_tour_done = fields.Boolean(
        string="LinkUp tour seen",
        copy=False,
        readonly=True,
        help="The member finished or skipped the first-use tour of LinkUp;"
        " it no longer starts by itself, on any device.",
    )
    # Read and written by LinkUp administrators only: a member neither sees
    # nor lifts their own suspension (LU-F-082 CA2).
    linkup_suspended_until = fields.Datetime(
        string="LinkUp suspension until",
        copy=False,
        groups=ADMIN_GROUP,
        help="Until this date, the member neither sends nor answers"
        " anything, and receives no reflection.",
    )

    def _linkup_has_group_id(self, xmlid):
        """Tell whether the user holds a group, implied groups included.

        It reads ``groups_id``, which holds the implied groups too, rather
        than ``has_group``: that one reports ``base.group_no_one`` only in
        debug mode, and its cache is stale inside a constraint that runs
        during the write of the groups.
        """
        self.ensure_one()
        group = self.env.ref(xmlid, raise_if_not_found=False)
        return bool(group) and group in self.groups_id

    def _linkup_is_restricted_member(self):
        """A LinkUp member who is not a system administrator."""
        self.ensure_one()
        return self._linkup_has_group_id(
            MEMBER_GROUP
        ) and not self._linkup_has_group_id("base.group_system")

    # ------------------------------------------------------------------
    # Suspension (LU-F-115 RM4)
    # ------------------------------------------------------------------

    def _linkup_is_suspended(self):
        """A restricted member whose suspension is not over yet."""
        self.ensure_one()
        until = self.sudo().linkup_suspended_until
        return (
            bool(until)
            and until > fields.Datetime.now()
            and self._linkup_is_restricted_member()
        )

    def _linkup_check_not_suspended(self):
        """Refuse an action that reaches another person to a suspended
        member, with the code of an unavailable sending."""
        if self._linkup_is_suspended():
            raise LinkupError(
                "linkup.unavailable",
                _(
                    "Your account is suspended: you cannot send anything for now."
                ),
            )

    def _linkup_check_admin(self):
        if not self.env.user._linkup_has_group_id(ADMIN_GROUP):
            raise AccessError(
                _("Only a LinkUp administrator can suspend a member.")
            )

    def action_linkup_suspend(self, until):
        """Suspend the members until ``until``, a datetime or its string
        form. A member writes no field of their own suspension; a LinkUp
        administrator does it here, under ``sudo``."""
        self._linkup_check_admin()
        until = fields.Datetime.to_datetime(until)
        if not until or until <= fields.Datetime.now():
            raise LinkupError(
                "linkup.validation",
                _("A suspension ends in the future."),
                field="linkup_suspended_until",
            )
        self.sudo().write({"linkup_suspended_until": until})
        return True

    def action_linkup_lift_suspension(self):
        """End the suspension of the members now."""
        self._linkup_check_admin()
        self.sudo().write({"linkup_suspended_until": False})
        return True

    def _linkup_set_home_action(self):
        """Give the LinkUp home action to members that have none.

        A home action already chosen for a user is kept.
        """
        action = self.env.ref(
            "mail_linkup_reflet.action_linkup_home", raise_if_not_found=False
        )
        if not action:
            return
        members = self.filtered(
            lambda user: not user.action_id
            and user._linkup_has_group_id(MEMBER_GROUP)
        )
        if members:
            members.sudo().write({"action_id": action.id})

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        users._linkup_set_home_action()
        return users

    def write(self, vals):
        res = super().write(vals)
        if "groups_id" in vals or any(is_reified_group(key) for key in vals):
            self._linkup_set_home_action()
        return res

    def _init_store_data(self, store: Store, /):
        """Tell the web client whether the current user is a LinkUp member.

        ``linkup_is_member`` shows the Reflection button of the composer and
        the LinkUp panel of a direct conversation; the server checks the
        group again on every action. ``linkup_max_hidden_themes`` bounds the
        choice of hidden themes in the form of a precision, as the server
        does. ``linkup_tour_pending`` starts the first-use tour, and the
        active highlights the member sent or received fill the Store.
        """
        super()._init_store_data(store)
        user = self.env.user
        is_member = not user._is_public() and user._linkup_has_group_id(
            MEMBER_GROUP
        )
        store.add(
            {
                "linkup_is_member": is_member,
                "linkup_max_hidden_themes": self.env[
                    "linkup.reflet.secret"
                ]._linkup_max_hidden_themes(),
                "linkup_tour_pending": is_member
                and not user.sudo().linkup_tour_done
                and self._linkup_first_use_tour_enabled(),
            }
        )
        if is_member:
            store.add(self.env["linkup.highlight"]._linkup_store_for(user))

    @api.model
    def _linkup_first_use_tour_enabled(self):
        """Whether the first-use tour starts by itself for new members."""
        value = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(FIRST_USE_TOUR_PARAM, "True")
        )
        return value != "False"

    @api.model
    def linkup_tour_consume(self):
        """Record that the current user finished or skipped the first-use
        tour, so that it no longer starts by itself.

        The other web clients of the user, already loaded with the tour
        pending, receive the new state over the bus: the tour no longer
        starts there either.
        """
        if not self.env.user._is_internal():
            raise AccessError(_("Only an internal user can do this."))
        self.env.user.sudo().linkup_tour_done = True
        self.env.user.partner_id._bus_send_store(
            {"linkup_tour_pending": False}
        )
        return True

    @api.model
    def _linkup_reset_first_use_tour(self):
        """Show the first-use tour again to every LinkUp member.

        Only a LinkUp administrator resets it. Return the number of members
        reset.
        """
        if not self.env.user._linkup_has_group_id(ADMIN_GROUP):
            raise AccessError(
                _("Only a LinkUp administrator can reset the tour.")
            )
        members = (
            self.sudo()
            .with_context(active_test=False)
            .search(
                [
                    ("linkup_tour_done", "=", True),
                    ("groups_id", "in", self.env.ref(MEMBER_GROUP).ids),
                ]
            )
        )
        members.write({"linkup_tour_done": False})
        return len(members)

    # ------------------------------------------------------------------
    # Signup through an invitation (LU-F-020)
    # ------------------------------------------------------------------

    @api.model
    def _linkup_signup_invited(self, values, invitation):
        """Create the account of a person signing up through the link of
        ``invitation``, and use the invitation for it.

        ``values`` holds ``login``, ``name``, ``password`` and ``lang``, as
        ``auth_signup`` prepares them; the login is an email address, which
        becomes the address of the account. The account copies the
        inactive member template: an internal user of the member group, with
        the Reflet view as home action. The signup needs no other
        authorization than the invitation, whatever
        ``auth_signup.invitation_scope`` says. The invitation then attaches
        its reflection to the account when its address is the invited one.

        A used, cancelled or expired invitation raises ``LinkupError``; an
        address already taken raises ``SignupError``, and the account is
        not created. Return ``(login, password)``.
        """
        invitation = invitation.sudo()
        invitation._linkup_lock()
        invitation._linkup_check_usable()
        login = email_normalize(values.get("login") or "")
        if not login:
            raise UserError(_("Enter a valid email address."))
        template = self.env.ref(
            MEMBER_TEMPLATE_XMLID, raise_if_not_found=False
        )
        if not template:
            raise SignupError(_("Signup: invalid template user"))
        vals = dict(values, login=login, email=login, active=True)
        try:
            with self.env.cr.savepoint():
                user = (
                    template.sudo()
                    .with_context(no_reset_password=True)
                    .copy(vals)
                )
        except Exception as error:
            raise SignupError(str(error)) from error
        invitation._linkup_consume(user)
        return user.login, values.get("password")

    @api.constrains("groups_id")
    def _check_linkup_member_technical_features(self):
        """Refuse the technical features group to a restricted member.

        ``base.group_no_one`` unlocks the developer tools in debug mode; a
        member who is not a system administrator never holds it.
        """
        for user in self:
            if user._linkup_is_restricted_member() and (
                user._linkup_has_group_id("base.group_no_one")
            ):
                raise ValidationError(
                    _(
                        "A LinkUp member cannot have the technical features"
                        " (%(user)s).",
                        user=user.name,
                    )
                )
