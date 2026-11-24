# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Server-side authorization of a join through the invitation link of a
channel.

``/chat/<id>/<token>`` adds the user of the request to the channel once the
token of that channel is checked. The controller of LinkUp marks that join
inside :func:`channel_invitation`; ``discuss.channel.member`` then lets a
member enter the channel by themself. The mark lives in a
``contextvars.ContextVar``: nothing a client sends reaches it, and it is
reset when the block ends, on error as well.
"""

import contextvars
from contextlib import contextmanager

_invited = contextvars.ContextVar(
    "linkup_channel_invitation", default=frozenset()
)


@contextmanager
def channel_invitation(channel_id):
    """Authorize the user of the request to join the channel
    ``channel_id``, whose invitation token the caller checked."""
    token = _invited.set(_invited.get() | {channel_id})
    try:
        yield
    finally:
        _invited.reset(token)


def invited_by_link(channel_id):
    """Whether the join of the channel ``channel_id`` comes from its
    invitation link."""
    return channel_id in _invited.get()
