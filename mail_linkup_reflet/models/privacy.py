# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""What a restricted member reads of the contact details of the other
people (LU-F-082 RM2, LU-F-112 RM3, CA3, LU-NF-009).

The address, the phone and the login of another person are never given to
a member, and never matched by their searches. The values are blanked in
what a reading returns, after the reading, so the cache of the server keeps
them. LinkUp administrators and system administrators read them all.
"""

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
# Fields of a message that hold the address of its author: Odoo writes
# ``email_from`` and ``reply_to`` from the address of the partner who posts.
AUTHOR_CONTACT_FIELDS = frozenset({"email_from", "reply_to"})


def contact_closed(env):
    """Whether the current user reads the contact details of themself only:
    a restricted member who is not a LinkUp administrator. ``sudo`` does not
    change it: the Discuss Store reads partners under ``sudo`` for the
    current user."""
    return env.user._linkup_is_plain_member()


def blank(field):
    """The value a reading gives for a field it keeps closed."""
    return [] if field.type in ("one2many", "many2many") else False


def mask_contact_rows(records, rows, fnames, contact_fields, own_id):
    """Blank, in ``rows`` read from ``records``, the fields of
    ``contact_fields`` of every row but ``own_id``."""
    contact = contact_fields.intersection(fnames)
    if not contact:
        return rows
    for vals in rows:
        if vals.get("id") == own_id:
            continue
        for fname in contact:
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
