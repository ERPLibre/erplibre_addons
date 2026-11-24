# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from datetime import datetime, time, timedelta

import pytz
from odoo import fields, models
from odoo.addons.mail.tools.discuss import Store
from odoo.addons.mail_linkup_reflet.models.res_users import MEMBER_GROUP

TIMEZONE_PARAM = "linkup.timezone"
DEFAULT_TIMEZONE = "America/Toronto"
MIN_ACCOUNT_HOURS_PARAM = "linkup.points_min_account_hours"
DEFAULT_MIN_ACCOUNT_HOURS = 72


class ResUsers(models.Model):
    _inherit = "res.users"

    # ------------------------------------------------------------------
    # Points
    # ------------------------------------------------------------------

    def _linkup_points_verified(self):
        """Tell whether the account of the member is verified.

        Every account is, until a module of the public signup adds the
        verification of the email address and overrides this method.
        """
        self.ensure_one()
        return True

    def _linkup_points_ineligibility(self):
        """Why the account earns no points yet, or ``False`` (§7.3).

        An account that is not verified, or that is younger than
        ``linkup.points_min_account_hours`` (72 hours by default), earns
        no points: a loop of new accounts confirming each other pays
        nothing.
        """
        self.ensure_one()
        user = self.sudo()
        if not user._linkup_points_verified():
            return "unverified"
        hours = self.env["linkup.reflet"]._linkup_param(
            MIN_ACCOUNT_HOURS_PARAM, DEFAULT_MIN_ACCOUNT_HOURS
        )
        if hours > 0 and (
            not user.create_date
            or user.create_date
            > fields.Datetime.now() - timedelta(hours=hours)
        ):
            return "new_account"
        return False

    def _linkup_timezone(self):
        """The time zone of the member: their own, else the one of the
        instance (``linkup.timezone``), else ``America/Toronto``."""
        self.ensure_one()
        names = (
            self.sudo().tz,
            self.env["ir.config_parameter"].sudo().get_param(TIMEZONE_PARAM),
            DEFAULT_TIMEZONE,
        )
        for name in names:
            if name and name in pytz.all_timezones_set:
                return pytz.timezone(name)
        return pytz.utc

    def _linkup_day_start(self, now):
        """Midnight of the day of ``now`` (naive UTC) in the time zone of
        the member, as a naive UTC datetime."""
        self.ensure_one()
        timezone = self._linkup_timezone()
        local = pytz.utc.localize(now).astimezone(timezone)
        start = timezone.localize(datetime.combine(local.date(), time.min))
        return start.astimezone(pytz.utc).replace(tzinfo=None)

    # ------------------------------------------------------------------
    # Ranks
    # ------------------------------------------------------------------

    def _rank_changed(self):
        """Announce the new rank of a restricted member on the bus only.

        The native method mails ``mail_template_data_new_rank_reached``; a
        member receives no email of the gamification (LU-F-102 RM2). Other
        users keep the native email.
        """
        members = self.filtered(
            lambda user: user._linkup_is_restricted_member()
        )
        for user in members:
            rank = user.rank_id.with_context(lang=user.lang)
            user.partner_id._bus_send(
                "linkup.points/rank",
                {
                    "rank_id": rank.id or False,
                    "name": rank.name or False,
                    "karma": user.karma,
                },
            )
        others = self - members
        if others:
            return super(ResUsers, others)._rank_changed()
        return None

    def _recompute_rank(self):
        """Take the rank away from a member whose karma fell below it.

        The native computation leaves the last rank to a karma that falls
        to 0 or below the lowest rank; a restricted member then holds no
        rank, and the lowest one is their next.
        """
        res = super()._recompute_rank()
        ranks = self.env["gamification.karma.rank"].search(
            [], order="karma_min"
        )
        stale = self.filtered(
            lambda user: user.rank_id
            and user.karma < user.rank_id.karma_min
            and user._linkup_is_restricted_member()
        )
        for user in stale:
            reached = ranks.filtered(lambda rank: rank.karma_min <= user.karma)
            rank = reached[-1:] if reached else ranks.browse()
            higher = ranks.filtered(lambda r: r.karma_min > user.karma)
            user.write({"rank_id": rank.id, "next_rank_id": higher[:1].id})
            user._rank_changed()
        return res

    # ------------------------------------------------------------------
    # Web client
    # ------------------------------------------------------------------

    def _init_store_data(self, store: Store, /):
        """Give a member their energy and rank (LU-F-071 RM1), the points of
        each rule of the scale, by code, for the texts that tell them, and
        the id of their newest ledger line: the lines above it are the ones
        the web client has not shown yet."""
        super()._init_store_data(store)
        user = self.env.user
        if user._is_public() or not user._linkup_has_group_id(MEMBER_GROUP):
            return
        me = user.sudo()
        last = (
            self.env["linkup.points.ledger"]
            .sudo()
            .search([("user_id", "=", user.id)], limit=1, order="id desc")
        )
        rules = self.env["linkup.points.rule"].sudo().search([])
        store.add(
            {
                "linkup_karma": me.karma,
                "linkup_rank": me.rank_id.name or False,
                "linkup_points_last_id": last.id or 0,
                "linkup_points_rules": {
                    rule.code: rule.points for rule in rules
                },
            }
        )
