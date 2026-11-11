# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import api, fields, models
from odoo.osv import expression
from odoo.tools import SQL

from .streamdeck_workstation import MANAGER_GROUP

DEVICE_MODEL = "streamdeck.device"


class StreamdeckThreadVisibility(models.AbstractModel):
    """What the current user reads of the thread of a deck.

    Mixed into `mail.message` and `mail.activity`, whose global read rule
    (`streamdeck_rules.xml`) asks for `streamdeck_visible_to_me`. A record
    about any other model is visible, and Odoo's own access decides. A
    record about a deck is visible to a Stream Deck manager, to the user
    named by `_streamdeck_user_field` when the model has one, and to a
    user whose `streamdeck.device.holding` of that deck has a `since` not
    after the record's `_streamdeck_date_field`: the bound that limits the
    history of the deck's events, so a new holder reads nothing of the
    thread from before their arrival, and a user who reads the deck
    through an event alone, holding nothing, reads nothing of it.
    """

    _name = "streamdeck.thread.visibility"
    _description = "Stream Deck thread visibility"

    _streamdeck_model_field = "model"
    _streamdeck_date_field = "date"
    _streamdeck_user_field = None

    streamdeck_visible_to_me = fields.Boolean(
        string="From my deck holding",
        compute="_compute_streamdeck_visible_to_me",
        search="_search_streamdeck_visible_to_me",
    )

    @api.depends_context("uid")
    def _compute_streamdeck_visible_to_me(self):
        ids = [record.id for record in self if isinstance(record.id, int)]
        visible = set(
            self.sudo()
            .with_context(active_test=False)
            .search(
                [("id", "in", ids), ("streamdeck_visible_to_me", "=", True)]
            )
            .ids
        )
        for record in self:
            record.streamdeck_visible_to_me = record.id in visible

    def _search_streamdeck_visible_to_me(self, operator, value):
        if operator not in ("=", "!=") or not isinstance(value, bool):
            raise NotImplementedError(
                "streamdeck_visible_to_me is searched with = or != and a"
                " boolean"
            )
        domain = self._streamdeck_visible_domain()
        if (operator == "=") != value:
            domain = ["!"] + domain
        return domain

    def _streamdeck_visible_domain(self):
        """The domain of the records the user of the environment reads,
        sudo or not."""
        if self.env.user.has_group(MANAGER_GROUP):
            return expression.TRUE_DOMAIN
        model_field = self._streamdeck_model_field
        date_field = self._streamdeck_date_field
        self.env["streamdeck.device.holding"].flush_model()
        self.flush_model([model_field, "res_id", date_field])
        held = SQL(
            "SELECT t.id FROM %s t"
            " JOIN streamdeck_device_holding h"
            " ON h.device_id = t.res_id AND h.since <= %s"
            " WHERE %s = %s AND h.user_id = %s",
            SQL.identifier(self._table),
            SQL.identifier("t", date_field),
            SQL.identifier("t", model_field),
            DEVICE_MODEL,
            self.env.uid,
        )
        domain = [
            "|",
            (model_field, "!=", DEVICE_MODEL),
            ("id", "in", SQL("(%s)", held)),
        ]
        if self._streamdeck_user_field:
            domain = [
                "|",
                (self._streamdeck_user_field, "=", self.env.uid),
            ] + domain
        return domain


class MailMessage(models.Model):
    _name = "mail.message"
    _inherit = ["mail.message", "streamdeck.thread.visibility"]


class MailActivity(models.Model):
    _name = "mail.activity"
    _inherit = ["mail.activity", "streamdeck.thread.visibility"]

    _streamdeck_model_field = "res_model"
    _streamdeck_date_field = "create_date"
    _streamdeck_user_field = "user_id"
