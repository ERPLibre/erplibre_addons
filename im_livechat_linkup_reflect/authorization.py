# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Server-side authorizations of the live chat of LinkUp.

Each one lives in a ``contextvars.ContextVar`` of this module: nothing a
client sends, neither a context key, nor a parameter, nor a field value,
reaches it, and it is reset when its block ends, on error as well.

:func:`distress_opening` lets the server open a conversation on the
distress channel, with the moderators it names: outside of it, that
channel has no operator, so ``/im_livechat/get_session`` opens nothing
there.

:func:`livechat_post` marks the carrier message of a reflection posted in
its live chat conversation, and :func:`bot_post` a message of the chatbot:
the start rule of a live chat lets both through.
"""

import contextvars
from contextlib import contextmanager

_distress_operators = contextvars.ContextVar(
    "linkup_distress_operators", default=None
)


@contextmanager
def distress_opening(user_ids):
    """Open the distress channel to the moderators ``user_ids`` for the
    duration of the block."""
    token = _distress_operators.set(frozenset(user_ids))
    try:
        yield
    finally:
        _distress_operators.reset(token)


def distress_operators():
    """The user ids the server opens the distress channel to, or ``None``
    outside :func:`distress_opening`."""
    return _distress_operators.get()


_livechat_post = contextvars.ContextVar("linkup_livechat_post", default=None)


@contextmanager
def livechat_post(reflet):
    """Mark the message posted in the block as the carrier of ``reflet`` on
    its live chat conversation."""
    token = _livechat_post.set((reflet.channel_id.id, reflet.id))
    try:
        yield
    finally:
        _livechat_post.reset(token)


def livechat_post_reflet_id(channel_id):
    """The id of the reflection whose carrier the server posts on the live
    chat conversation ``channel_id``, or ``None``."""
    post = _livechat_post.get()
    if post and post[0] == channel_id:
        return post[1]
    return None


_bot_post = contextvars.ContextVar("linkup_bot_post", default=None)


@contextmanager
def bot_post(channel_ids):
    """Mark the messages posted in the block as written by the chatbot on
    the conversations ``channel_ids``."""
    token = _bot_post.set(frozenset(channel_ids))
    try:
        yield
    finally:
        _bot_post.reset(token)


def in_bot_post(channel_id):
    """Tell whether the chatbot posts on the conversation ``channel_id``."""
    channel_ids = _bot_post.get()
    return bool(channel_ids) and channel_id in channel_ids
