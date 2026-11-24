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
# Models whose records hold the photo of a person, a user through its
# partner.
PHOTO_MODELS = ("res.partner", "res.users")


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


def closed_photo_partner_ids(env, partner_ids):
    """The ids of ``partner_ids`` whose photo the current user does not
    read: for a restricted member, every partner but their own and those
    of their ``active`` links; for anybody else, none."""
    if not contact_closed(env):
        return set()
    ids = set(partner_ids) - {env.user.partner_id.id, False}
    if not ids:
        return ids
    linked = env["res.users"].sudo().browse(linked_user_ids(env))
    return ids - set(linked.partner_id.ids)


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


def export_photo_mask(records, fields, photo_fields, owner):
    """The mask of the photos in an export of ``records`` by a restricted
    member (``linkup.contact.privacy._linkup_export_masks``):
    ``(indexes, kept)``, the columns of ``fields`` that hold a photo of
    ``photo_fields`` and the records whose photo the reader reads, or
    ``None``. ``owner`` gives the partner of a record, read under
    ``sudo``."""
    if not contact_closed(records.env):
        return None
    columns = [
        index
        for index, path in enumerate(fields)
        if len(path) == 1 and path[0] in photo_fields
    ]
    if not columns:
        return None
    owners = {record.id: owner(record.sudo()).id for record in records}
    closed = closed_photo_partner_ids(records.env, owners.values())
    kept = records.filtered(lambda record: owners[record.id] not in closed)
    return columns, kept
