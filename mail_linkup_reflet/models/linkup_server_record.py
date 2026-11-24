# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import api, models
from odoo.tools import clean_context


class LinkupServerRecord(models.AbstractModel):
    """A record LinkUp writes on the server only, under ``sudo``.

    Such a creation names the fields it sets and leaves the others to
    their defaults. A ``default_<field>`` key of the context, which a
    client sets as it likes, would fill them instead: the urgency of a
    report, the date of a consent or of a row of the audit log. The
    defaults of these models are those of their fields only, whatever the
    context holds.
    """

    _name = "linkup.server.record"
    _description = "LinkUp record written by the server"

    @api.model
    def default_get(self, fields_list):
        return super(
            LinkupServerRecord,
            self.with_context(clean_context(self.env.context)),
        ).default_get(fields_list)
