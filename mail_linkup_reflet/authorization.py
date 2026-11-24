# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Server-side authorization of the posts of a reflection.

A ``linkup.reflet`` method opens the direct conversation of a pair and posts
the carrier message of a reflection inside :func:`linkup_post`. The
authorization lives in a ``contextvars.ContextVar`` of this module: nothing
a client sends, neither a context key, nor a parameter, nor a field value,
reaches it, and it is reset when the block ends, on error as well.

It covers one reflection, its author as the acting user, and the partners of
its two parties; the code that honours it checks all three.

:func:`channel_post` marks, the same way, the creation of the messages of a
conversation by ``discuss.channel.message_post``: outside of it, a member
never creates a message of a conversation through the ORM.

:func:`server_notification` marks the notifications that a Discuss method
writes itself; the start rule lets only those through as ``notification``.
"""

import contextvars
from contextlib import contextmanager
from dataclasses import dataclass


@dataclass(frozen=True)
class LinkupPost:
    """The post in progress: the reflection, its author, its two parties."""

    reflet_id: int
    uid: int
    partner_ids: frozenset


_current_post = contextvars.ContextVar("linkup_post", default=None)


@contextmanager
def linkup_post(reflet):
    """Authorize the author of ``reflet`` to reach its recipient and to post
    its carrier message, for the duration of the block."""
    reflet = reflet.sudo()
    token = _current_post.set(
        LinkupPost(
            reflet_id=reflet.id,
            uid=reflet.author_id.id,
            partner_ids=frozenset(
                (
                    reflet.author_id.partner_id
                    | reflet.recipient_id.partner_id
                ).ids
            ),
        )
    )
    try:
        yield
    finally:
        _current_post.reset(token)


def current_post(env):
    """The post in progress for the user of ``env``, or ``None``.

    An authorization opened for another user is never returned, so a call
    made in the same thread on behalf of somebody else does not inherit it.
    """
    post = _current_post.get()
    if post and post.uid == env.uid:
        return post
    return None


_channel_post = contextvars.ContextVar("linkup_channel_post", default=None)


@contextmanager
def channel_post(channel_ids):
    """Mark the messages created in the block as posted on the
    conversations ``channel_ids`` through ``message_post``."""
    token = _channel_post.set(frozenset(channel_ids))
    try:
        yield
    finally:
        _channel_post.reset(token)


def in_channel_post(channel_id):
    """Tell whether ``message_post`` of conversation ``channel_id`` is
    creating its message."""
    channel_ids = _channel_post.get()
    return bool(channel_ids) and channel_id in channel_ids


_server_notification = contextvars.ContextVar(
    "linkup_server_notification", default=False
)


@contextmanager
def server_notification():
    """Mark the ``notification`` messages posted in the block as written by
    the server: the text is the one of a Discuss method (a pin, a member
    joining), never one a client sends."""
    token = _server_notification.set(True)
    try:
        yield
    finally:
        _server_notification.reset(token)


def in_server_notification():
    """Tell whether a Discuss method is posting its own notification."""
    return _server_notification.get()
