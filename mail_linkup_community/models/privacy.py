# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""The photo of the other members, for a restricted member (LU-F-082 RM3,
Q-27).

The photo of another member reaches only the members with whom they share
an ``active`` link; the others see their pseudonym. The values are blanked
in what a reading returns, after the reading, so the cache of the server
keeps them. The contact details of the others are closed by the module of
the reflections (``mail_linkup_reflet.models.privacy``).
"""

from odoo.addons.mail_linkup_reflet.models.privacy import (  # noqa: F401
    blank,
    contact_closed,
)

# The photo, in every size.
IMAGE_FIELDS = frozenset(
    {
        f"{kind}_{size}"
        for kind in ("image", "avatar")
        for size in (1920, 1024, 512, 256, 128)
    }
)


def linked_user_ids(env):
    """The users with whom the current user shares an ``active`` link."""
    uid = env.uid
    links = (
        env["linkup.link"]
        .sudo()
        .search(
            [
                ("state", "=", "active"),
                "|",
                ("user_a_id", "=", uid),
                ("user_b_id", "=", uid),
            ]
        )
    )
    return set((links.user_a_id | links.user_b_id).ids) - {uid}


def mask_images(records, rows, fnames, own_id, linked):
    """Blank, in ``rows`` read from ``records``, the photo of every row
    neither ``own_id`` nor in the ids that ``linked()`` returns.

    ``linked`` is called only when a photo is read: the readings of the
    Discuss Store, which ask for no photo, then run no query of the links
    of the reader, whose number grows with their contacts.
    """
    images = IMAGE_FIELDS.intersection(fnames)
    if not images:
        return rows
    linked_ids = linked()
    for vals in rows:
        row_id = vals.get("id")
        if row_id == own_id or row_id in linked_ids:
            continue
        for fname in images:
            if fname in vals:
                vals[fname] = blank(records._fields[fname])
    return rows
