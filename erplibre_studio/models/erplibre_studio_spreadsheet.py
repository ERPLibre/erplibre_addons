# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from lxml import etree
from odoo import fields, models

from .. import arch as studio_arch
from .erplibre_studio_project import PREVIEW_KEY

# How many rows a sheet made from a list shows at most, as the list view of
# spreadsheet_oca offers its number of rows: the records of a page.
SPREADSHEET_LIST_ROWS = 80


class ErplibreStudioSpreadsheet(models.Model):
    """A spreadsheet of spreadsheet_oca the editor created from a list, a
    pivot or a graph view (``send_to_spreadsheet``): which model and view
    it reads. Revert, an Apply and the uninstall of the generated module
    report these sheets and delete those whose model they remove.
    ``sheet_id`` is the id of the spreadsheet.spreadsheet, an
    integer: the studio does not depend on spreadsheet_oca, whose model
    exists only once it is installed, and a sheet deleted by hand leaves
    an id that ``exists()`` filters out."""

    _name = "erplibre.studio.spreadsheet"
    _description = "Studio spreadsheet"
    _order = "id"

    project_id = fields.Many2one(
        "erplibre.studio.project",
        required=True,
        ondelete="cascade",
        index=True,
    )
    name = fields.Char()
    model = fields.Char(required=True)
    view_type = fields.Char(required=True)
    view_id = fields.Many2one("ir.ui.view", ondelete="set null")
    sheet_id = fields.Integer(string="Spreadsheet", required=True)


class ErplibreStudioProject(models.Model):
    """The spreadsheets the editor sends the views of a project to: the
    import data of spreadsheet_oca, and what Revert does with them."""

    _inherit = "erplibre.studio.project"

    def _studio_view_unapplied(self, view):
        """Whether ``view``, a view of the database, has changes in the draft
        that the last Apply did not write: its changes differ from those
        of the applied snapshot."""
        self.ensure_one()
        current = self._view_changes(view)._snapshot()
        applied = [
            item
            for item in self._studio_load_snapshot(self.applied_snapshot)["changes"]
            if item.get("view_id") == view.id
        ]
        return current != applied

    def _studio_spreadsheet_action_xmlid(self, model):
        """The external id of the window action Apply created for ``model``,
        a model the project creates, or False."""
        self.ensure_one()
        line = self.new_model_ids.filtered(lambda m: m.model == model)[:1]
        if not line:
            return False
        name = line._studio_xml_names()["action"]
        if not self._studio_record("ir.actions.act_window", name):
            return False
        return f"{self.module_name}.{name}"

    def _studio_spreadsheet_import_data(self, model, view, view_type):
        """The ``import_data`` the client action of spreadsheet_oca reads
        (« action_spreadsheet_oca ») to fill a new sheet from ``view``, a
        primary ``view_type`` view of ``model`` (SPREADSHEET_VIEW_TYPES), as
        its own list, pivot and graph views give it: the arch the database
        serves, with its inherited views, read by
        ``arch.spreadsheet_source``; every record, no search. The keys are
        the contract of spreadsheet_oca with its views, not a public API:
        the tests pin them."""
        self.ensure_one()
        Model = self.env[model].with_context(**{PREVIEW_KEY: False})
        root = etree.fromstring(Model.get_view(view.id, view_type)["arch"])
        fields_info = {
            name: {**info, "name": name} for name, info in Model.fields_get().items()
        }
        source = studio_arch.spreadsheet_source(root, view_type, fields_info)
        label = self.env["ir.model"]._get(model).name or model
        type_label = (
            self.env["erplibre.studio.editor"]
            ._view_type_labels()
            .get(view_type, view_type)
        )
        name = self.env._("%(model)s · %(view)s", model=label, view=type_label)
        if view_type == "list":
            data = {
                "mode": "list",
                "metaData": {
                    "model": model,
                    "domain": "[]",
                    "orderBy": source["orderBy"],
                    "context": {},
                    "columns": source["columns"],
                    "fields": fields_info,
                    "name": name,
                },
                "dyn_number_of_rows": min(
                    Model.search_count([]), SPREADSHEET_LIST_ROWS
                ),
            }
        elif view_type == "pivot":
            data = {
                "mode": "pivot",
                "metaData": {
                    "resModel": model,
                    "fields": fields_info,
                    "activeMeasures": source["activeMeasures"],
                    "rowGroupBys": source["rowGroupBys"],
                    "colGroupBys": source["colGroupBys"],
                    "expandedRowGroupBys": [],
                    "expandedColGroupBys": [],
                    "sortedColumn": None,
                    "title": source["title"] or label,
                },
                "searchParams": {"domain": "[]", "context": {}},
            }
        else:
            data = {
                "mode": "graph",
                "metaData": {
                    "mode": source["mode"],
                    "measure": source["measure"],
                    "groupBy": source["groupBy"],
                    "order": source["order"],
                    "stacked": source["stacked"],
                    "cumulated": source["cumulated"],
                    "cumulatedStart": source["cumulatedStart"],
                    "resModel": model,
                    "fields": fields_info,
                    "fieldAttrs": {},
                    "title": source["title"] or label,
                },
                "searchParams": {
                    "context": {},
                    "domain": "[]",
                    "groupBy": [],
                    "orderBy": [],
                },
            }
        data["name"] = name
        data["new"] = 1
        action = self._studio_spreadsheet_action_xmlid(model)
        if action:
            data["actionXmlId"] = action
        return data

    def _studio_spreadsheets(self):
        """The spreadsheet.spreadsheet records of the tracking rows that
        still exist, in sudo, by tracking row: {row: sheet}. Empty without
        spreadsheet_oca."""
        if "spreadsheet.spreadsheet" not in self.env:
            return {}
        Sheet = (
            self.env["spreadsheet.spreadsheet"].sudo().with_context(active_test=False)
        )
        sheets = {}
        for row in self.spreadsheet_ids:
            sheet = Sheet.browse(row.sheet_id).exists()
            if sheet:
                sheets[row] = sheet
        return sheets

    def _studio_spreadsheet_report(self, removed_models, deleted_only=False):
        """[{name, model, deleted}] of the existing sheets of the project,
        in the order they were sent: ``deleted`` when their model is among
        ``removed_models`` (the operation deletes them), else they stay;
        with ``deleted_only``, the deleted ones alone. A read."""
        self.ensure_one()
        items = [
            {
                "name": sheet.name or "",
                "model": row.model,
                "deleted": row.model in removed_models,
            }
            for row, sheet in self._studio_spreadsheets().items()
        ]
        if deleted_only:
            return [item for item in items if item["deleted"]]
        return items

    def _studio_drop_spreadsheets(self, removed_models):
        """Delete, in sudo, the sheets of the project whose model is among
        ``removed_models``, with their tracking rows: a sheet whose model
        left the database reads nothing."""
        self.ensure_one()
        sheets = self._studio_spreadsheets()
        rows = self.spreadsheet_ids.filtered(lambda row: row.model in removed_models)
        for row in rows:
            if row in sheets:
                sheets[row].unlink()
        rows.sudo().unlink()

    def _studio_revert_spreadsheets(self, removed_models):
        """Delete the sheets whose model Revert removed (``removed_models``,
        ``_studio_drop_spreadsheets``), then every tracking row of the
        project: the sheets that stay are no longer the project's."""
        self.ensure_one()
        self._studio_drop_spreadsheets(removed_models)
        self.spreadsheet_ids.sudo().unlink()
