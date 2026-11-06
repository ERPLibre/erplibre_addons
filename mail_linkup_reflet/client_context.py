# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""The context a public method of LinkUp runs with.

A client sets the whole context of a call: ``call_kw``, ``/jsonrpc`` and
the ``context`` parameter of a JSON route all pass it on as they receive
it. Some keys widen what the server does under ``sudo``: ``active_test``
turned off lets archived accounts, conversations and rules into its
searches, a ``default_<field>`` key fills the fields a creation leaves
out, and a key a module reads changes its behaviour.

:func:`server_context` runs a public method with the keys of
``CLIENT_KEYS`` only, which change the form of an answer, never what it
holds. The server sets the other keys itself, inside the method.
"""

import functools

# The language and time zone of the answer, and the companies of the
# session, which the environment checks against those of the user.
CLIENT_KEYS = frozenset({"lang", "tz", "uid", "allowed_company_ids"})


def client_context(context):
    """The keys of ``context`` a public method keeps."""
    return {key: value for key, value in context.items() if key in CLIENT_KEYS}


def server_context(method):
    """Run ``method`` with the context of its caller reduced to
    ``CLIENT_KEYS``.

    It goes under ``api.model`` when both apply, so that ``call_kw`` still
    reads the kind of the method.
    """

    @functools.wraps(method)
    def call(self, *args, **kwargs):
        if not CLIENT_KEYS.issuperset(self.env.context):
            self = self.with_context(client_context(self.env.context))
        return method(self, *args, **kwargs)

    return call
