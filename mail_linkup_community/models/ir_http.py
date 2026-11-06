# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import logging

from odoo import api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# The action under which every signup entry of LinkUp asks for the proof
# of a human: /web/signup and the page of an invitation link.
SIGNUP_ACTION = "signup"


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @api.model
    def _verify_request_recaptcha_token(self, action):
        """Check the anti-robot proof of a signup, and refuse a missing or
        invalid one with the neutral error of a signup.

        ``website_altcha`` checks the ``altcha`` parameter of the request
        once the website holds an ``altcha_key``; without that key, every
        request passes, as before the module. A refusal, a ``False`` or a
        ``UserError`` of any provider, becomes "Could not create a new
        account.", the answer of the other refusals of a signup: it names
        no provider, and it comes before any lookup of the address, so it
        is the same whatever the address. Other actions keep the answer of
        their provider."""
        if action != SIGNUP_ACTION:
            return super()._verify_request_recaptcha_token(action)
        try:
            verified = super()._verify_request_recaptcha_token(action)
        except UserError as error:
            _logger.info("LinkUp: signup refused by the captcha: %s", error)
            verified = False
        if not verified:
            raise UserError(self.env._("Could not create a new account."))
        return verified
