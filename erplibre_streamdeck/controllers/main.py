# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""HTTP routes of the workstation protocol 1.0, under `/streamdeck/v1/`.

Each route takes a POST whose body is a JSON object and answers a JSON
object with the status that `streamdeck.service` returns; a body that is
not JSON answers 400 `bad_request` without reaching the service. Another
HTTP method is answered 405 by the router.

The routes run with `auth="none"`: the client chooses the database
beforehand with `GET /web/login?db=<db>` and sends the session cookie it
receives. `report` and `unenroll` read the workstation token from the
header `Authorization: Bearer <token>`; a missing or malformed header
reaches the service as no token, which answers 401 `token_invalid`.

Neither the body, the headers nor the reply are logged, and the reply is
marked `Cache-Control: no-store`: `enroll` returns the workstation token.
"""

import json

from odoo import SUPERUSER_ID, http
from odoo.http import request

from ..models.streamdeck_service import PROTOCOL

BASE = "/streamdeck/v1/"
ROUTE_OPTIONS = {
    "type": "http",
    "auth": "none",
    "csrf": False,
    "methods": ["POST"],
    "save_session": False,
    # Odoo opens a route with `auth="none"` on a read-only cursor unless
    # told otherwise; every route here writes.
    "readonly": False,
}


def _payload():
    """The decoded JSON body; None when the body is not JSON. The body
    may be UTF-8, UTF-16 or UTF-32, as `json.loads` detects; nesting too
    deep for the decoder counts as not JSON."""
    try:
        return json.loads(request.httprequest.get_data())
    except (ValueError, RecursionError):
        return None


def _bearer():
    """The token of an `Authorization: Bearer <token>` header, the scheme
    read without regard to case; None for any other form."""
    parts = request.httprequest.headers.get("Authorization", "").split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None


def _answer(status, body):
    # json.dumps escapes non-ASCII characters, so the body is ASCII and
    # its length in characters is its length in bytes.
    data = json.dumps(body)
    return request.make_response(
        data,
        headers=[
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(data))),
            ("Cache-Control", "no-store"),
        ],
        status=status,
    )


class StreamdeckController(http.Controller):
    def _serve(self, method, with_token):
        """Decode the body and call `streamdeck.service.<method>` as the
        superuser, with the bearer token first when `with_token`."""
        payload = _payload()
        if payload is None:
            return _answer(400, {"protocol": PROTOCOL, "error": "bad_request"})
        service = request.env(user=SUPERUSER_ID)["streamdeck.service"]
        args = (_bearer(), payload) if with_token else (payload,)
        return _answer(*getattr(service, method)(*args))

    @http.route(BASE + "enroll", **ROUTE_OPTIONS)
    def enroll(self):
        return self._serve("enroll", with_token=False)

    @http.route(BASE + "report", **ROUTE_OPTIONS)
    def report(self):
        return self._serve("report", with_token=True)

    @http.route(BASE + "unenroll", **ROUTE_OPTIONS)
    def unenroll(self):
        return self._serve("unenroll", with_token=True)
