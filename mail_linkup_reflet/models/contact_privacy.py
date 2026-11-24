# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from itertools import groupby

from odoo import _, api, models
from odoo.exceptions import AccessError
from odoo.tools import SQL

from . import privacy


class LinkupContactPrivacy(models.AbstractModel):
    """The readings of the contact details that pass by neither
    ``_read_format`` nor ``_condition_to_sql`` (LU-NF-009, LU-F-112 RM3).

    ``read_group`` and ``web_read_group`` build a grouping or an aggregate
    straight from the column, an order compares the values, and
    ``export_data`` reads them from the cache. For a restricted member
    outside ``sudo``: a grouping or an aggregate on a closed field is
    refused, an order on it is left out, and an export blanks it in every
    row but their own. A model lists its closed fields in
    ``_linkup_contact_fields`` and gives the rows that are the reader's
    own with ``_linkup_contact_own``; ``_linkup_export_masks`` lets
    another module blank more columns of an export.
    """

    _name = "linkup.contact.privacy"
    _description = "LinkUp contact details closed to a member"

    _linkup_contact_fields = frozenset()

    def _linkup_contact_own(self):
        """The records of ``self`` whose contact details are the reader's
        own."""
        return self.browse()

    def _linkup_contact_closed(self, spec):
        """Whether the field of ``spec`` (``field``, ``field:aggregate``,
        ``field.path``) is closed to the reader."""
        fname = spec.split(":", 1)[0].split(".", 1)[0]
        return privacy.search_closed(self, fname, self._linkup_contact_fields)

    def _linkup_contact_refuse(self, spec):
        if self._linkup_contact_closed(spec):
            raise AccessError(
                _(
                    "A LinkUp member does not group the contact details of"
                    " the other people."
                )
            )

    @api.model
    def _read_group_select(self, aggregate_spec, query):
        self._linkup_contact_refuse(aggregate_spec)
        return super()._read_group_select(aggregate_spec, query)

    @api.model
    def _read_group_groupby(self, groupby_spec, query):
        self._linkup_contact_refuse(groupby_spec)
        return super()._read_group_groupby(groupby_spec, query)

    def _order_field_to_sql(self, alias, field_name, direction, nulls, query):
        """Leave out of an order the closed fields: comparing a hidden
        value with a known one would reveal it, one search after another.
        An empty term is dropped by ``_order_to_sql``."""
        if self._linkup_contact_closed(field_name):
            return SQL()
        return super()._order_field_to_sql(
            alias, field_name, direction, nulls, query
        )

    def _linkup_export_masks(self, fields):
        """The columns an export of ``self`` blanks, as a list of
        ``(indexes, kept)``: the indexes of columns of ``fields`` blanked
        in every row but those of the records of ``kept``. The closed
        contact fields keep the reader's own records; another module adds
        its own columns."""
        columns = [
            index
            for index, path in enumerate(fields)
            if len(path) == 1 and self._linkup_contact_closed(path[0])
        ]
        return [(columns, self._linkup_contact_own())] if columns else []

    def _export_rows(self, fields, *, _is_toplevel_call=True):
        """Blank the closed columns of the exported rows
        (``_linkup_export_masks``). The records are exported in runs of
        records that keep the same columns, in their order: a record may
        take several rows, the lines of its one2many fields, which only
        its run then holds. A path through a relation reaches the
        ``_export_rows`` of its model."""
        masks = self._linkup_export_masks(fields)
        if not masks:
            return super()._export_rows(
                fields, _is_toplevel_call=_is_toplevel_call
            )
        lines = []
        for opened, run in groupby(
            self,
            key=lambda record: tuple(record in kept for __, kept in masks),
        ):
            records = self.browse([record.id for record in run])
            rows = super(LinkupContactPrivacy, records)._export_rows(
                fields, _is_toplevel_call=_is_toplevel_call
            )
            blanked = [
                index
                for (columns, __), is_open in zip(masks, opened)
                if not is_open
                for index in columns
            ]
            for row in rows:
                for index in blanked:
                    row[index] = ""
            lines += rows
        return lines
