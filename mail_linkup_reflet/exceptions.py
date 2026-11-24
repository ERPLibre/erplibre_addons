# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo.exceptions import UserError

# The error catalogue shared by the web and mobile clients (LU-F-093): the
# only codes a LinkupError carries. A client maps each one to its own
# translated message and never shows the text of the server.
#
# ``linkup.cap_reached`` is an information about the points of an action
# that succeeded, raised by the scoring module; ``linkup.not_verified`` and
# ``linkup.consent_required`` belong to the public signup. They are part of
# the catalogue so that the clients know them before these modules raise
# them.
LINKUP_ERROR_CODES = frozenset(
    {
        "linkup.unavailable",
        "linkup.already_answered",
        "linkup.expired",
        "linkup.cap_reached",
        "linkup.rate_limited",
        "linkup.start_rule",
        "linkup.not_verified",
        "linkup.consent_required",
        "linkup.invite_expired",
        "linkup.invite_used",
        "linkup.invite_cancelled",
        "linkup.validation",
    }
)


class LinkupError(UserError):
    """A refused LinkUp action, carrying a stable code for the clients.

    ``odoo.http.serialize_exception`` copies the ``context`` attribute of an
    exception into ``error.data.context``: the web and mobile clients read
    ``linkup_code`` there and never the translated message. ``code`` must
    be one of ``LINKUP_ERROR_CODES``; any other value raises ``ValueError``,
    so that a client never meets a code it does not know.
    ``linkup.validation`` also names the faulty field in ``linkup_field``,
    and the maximum length of a text too long in ``linkup_limit``.
    """

    def __init__(self, code, message, field=None, limit=None):
        if code not in LINKUP_ERROR_CODES:
            raise ValueError(f"Unknown LinkUp error code: {code}")
        super().__init__(message)
        self.code = code
        self.context = {"linkup_code": code}
        if field:
            self.context["linkup_field"] = field
        if limit:
            self.context["linkup_limit"] = limit
