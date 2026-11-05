# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import http
from odoo.addons.mail.controllers.thread import ThreadController


class LinkupThreadController(ThreadController):
    @http.route()
    def mail_message_post(
        self, thread_model, thread_id, post_data, context=None, **kwargs
    ):
        """Drop the ``linkup`` keys of the context a client sends.

        The route copies that context into the one of the request. No
        authorization of LinkUp reads the context, which a client controls:
        the post of a reflection is recognised by ``authorization``, out of
        reach of a request. Dropping the keys keeps a client value from ever
        meeting a LinkUp key.
        """
        if context:
            context = {
                key: value
                for key, value in context.items()
                if not str(key).startswith("linkup")
            }
        return super().mail_message_post(
            thread_model, thread_id, post_data, context=context, **kwargs
        )
