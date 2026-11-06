# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import api, fields, models

CALL_MIN_DURATION_PARAM = "linkup.call_min_duration"


class LinkupPointsCall(models.Model):
    """An answered call whose points wait for its end.

    When ``linkup.call_min_duration`` is above 0, an answered call is paid
    when it ends, and only if it lasted that many seconds since its answer
    (§7.3). A call ends when its conversation holds fewer than two RTC
    sessions: one participant left, or the server closed an inactive
    session.
    """

    _name = "linkup.points.call"
    _inherit = ["linkup.server.record"]
    _description = "LinkUp answered call waiting for its end"

    code = fields.Char(required=True)
    link_id = fields.Many2one(
        "linkup.link", string="Link", required=True, ondelete="cascade"
    )
    channel_id = fields.Many2one(
        "discuss.channel",
        string="Conversation",
        required=True,
        index=True,
        ondelete="cascade",
    )
    reflet_id = fields.Many2one(
        "linkup.reflet", string="Reflection", ondelete="set null"
    )
    event_key = fields.Char(string="Event key", required=True)
    answered_date = fields.Datetime(string="Answered on", required=True)

    _sql_constraints = [
        ("event_unique", "UNIQUE(event_key)", "A call waits once."),
    ]

    @api.model
    def _linkup_min_duration(self):
        """Seconds an answered call lasts to be paid; 0 pays at once."""
        return max(
            0,
            self.env["linkup.reflet"]._linkup_param(
                CALL_MIN_DURATION_PARAM, 0
            ),
        )

    @api.model
    def _linkup_wait(self, code, link, reflet, channel, key):
        """Keep an answered call until its end."""
        if not (link and channel and key):
            return self.browse()
        if self.search_count([("event_key", "=", key)]):
            return self.browse()
        return self.create(
            {
                "code": code,
                "link_id": link.id,
                "channel_id": channel.id,
                "reflet_id": reflet.id or False,
                "event_key": key,
                "answered_date": fields.Datetime.now(),
            }
        )

    @api.model
    def _linkup_close_ended(self, channels):
        """Pay the calls of ``channels`` that ended after the minimum
        duration, and forget every call that ended."""
        if not channels:
            return
        minimum = self._linkup_min_duration()
        now = fields.Datetime.now()
        Rule = self.env["linkup.points.rule"]
        for call in self.search([("channel_id", "in", channels.ids)]):
            if len(call.channel_id.rtc_session_ids) >= 2:
                continue
            if (now - call.answered_date).total_seconds() >= minimum:
                link = call.link_id
                Rule._linkup_apply_event(
                    call.code,
                    link.user_a_id | link.user_b_id,
                    link=link,
                    reflet=call.reflet_id,
                    channel=call.channel_id,
                    key=call.event_key,
                )
            call.unlink()
