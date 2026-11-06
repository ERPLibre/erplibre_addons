# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""What a restricted member reads of the other people (LU-F-082 RM2, RM3,
LU-F-112 RM3, LU-NF-009, Q-27).

The contact details of another person, address, phone and login, are
never given to a member, and never matched by their searches. The photo of
another member reaches only the members with whom they share an ``active``
link; the others see their pseudonym. The values are blanked in what a
reading returns, after the reading, so the cache of the server keeps them.
"""

from odoo.addons.mail_linkup_reflet.models.res_users import (
    ADMIN_GROUP,
    MEMBER_GROUP,
)

# Contact details of a partner, and of a user through its partner.
CONTACT_FIELDS = frozenset(
    {
        "email",
        "email_normalized",
        "email_formatted",
        "phone",
        "mobile",
        "phone_sanitized",
        "phone_mobile_search",
    }
)
USER_CONTACT_FIELDS = CONTACT_FIELDS | {"login"}
# The photo, in every size.
IMAGE_FIELDS = frozenset(
    {
        f"{kind}_{size}"
        for kind in ("image", "avatar")
        for size in (1920, 1024, 512, 256, 128)
    }
)


def contact_closed(env):
    """Whether the current user reads the contact details of themself only:
    a restricted member who is not a LinkUp administrator. ``sudo`` does not
    change it: the Discuss Store reads partners under ``sudo`` for the
    current user."""
    user = env.user
    if user._is_public() or not user._is_internal():
        return False
    return user._linkup_has_group_id(MEMBER_GROUP) and not (
        user._linkup_has_group_id(ADMIN_GROUP)
        or user._linkup_has_group_id("base.group_system")
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


def blank(field):
    return [] if field.type in ("one2many", "many2many") else False


def mask_rows(records, rows, fnames, contact_fields, own_id, linked_ids):
    """Blank, in ``rows`` read from ``records``, the contact fields of every
    row but ``own_id``, and the photo of every row neither ``own_id`` nor in
    ``linked_ids``."""
    contact = contact_fields.intersection(fnames)
    images = IMAGE_FIELDS.intersection(fnames)
    if not contact and not images:
        return rows
    for vals in rows:
        row_id = vals.get("id")
        if row_id == own_id:
            continue
        for fname in contact:
            if fname in vals:
                vals[fname] = blank(records._fields[fname])
        if row_id not in linked_ids:
            for fname in images:
                if fname in vals:
                    vals[fname] = blank(records._fields[fname])
    return rows


def search_closed(model, fname, contact_fields):
    """Whether a condition of a search on ``fname`` of ``model`` must match
    nothing: a contact field, searched by a restricted member outside
    ``sudo``. The conditions reach here from any domain, the ones that
    ``display_name`` or a path builds included."""
    return (
        fname in contact_fields
        and not model.env.su
        and contact_closed(model.env)
    )
