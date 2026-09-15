#!/usr/bin/env python3
# © 2021-2025 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
import json
import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

DEFAULT_CRON_CODE_SCAFFOLD = (
    "# TODO: link mirror rows to their target by chained natural keys, then\n"
    "# create sync.data.transform.exec rows (use modification_text, NOT\n"
    "# modification). See addons/safirh/data/ir_cron.xml for the pattern.\n"
    "transform = env['sync.data.transform'].create({})\n"
)


class DevopsCgModel(models.Model):
    _inherit = "devops.cg.model"

    IGNORE_SYNC_FIELD_NAME = ["file_no_line", "company_currency_id"]

    enable_sync_external = fields.Boolean(
        string="Enable sync_external",
        help="Feature associate with sync external",
    )

    sync_external_file_type = fields.Selection(
        selection=[("csv", "CSV"), ("xlsx", "Excel")],
        help="Feature associate with synx external",
        default="csv",
    )

    sync_external_index_line_header = fields.Integer(
        help="Indicate the line number of header. Default 0 for CSV, and 1 for Excel",
        compute="_compute_index_line_header",
        store=True,
        readonly=False,
    )

    # sync_external_skip = fields.Integer(
    #     help="Indicate the line number of header. Default 0 for CSV, and 1 for Excel",
    #     compute="_compute_index_line_header",
    #     store=True,
    #     readonly=False,
    # )

    sync_external_sheet_name = fields.Char(help="Can be Sheet0 or Sheet1")

    sync_external_scenario = fields.Char(
        help="sync.model scenario name (optional)"
    )

    sync_external_context_name = fields.Char(
        help=(
            "sync.model context_name; drives the transform branch at runtime"
            " (optional)"
        )
    )

    sync_external_description = fields.Text(
        help="sync.model description (optional)"
    )

    sync_external_ignore_data = fields.Text(
        help="Values coerced to False during import, one per line"
    )

    sync_external_nb_line_header = fields.Integer(
        default=1,
        help="Number of header lines to concatenate",
    )

    sync_external_bind_ids = fields.One2many(
        comodel_name="devops.cg.sync.bind",
        inverse_name="model_id",
        string="Bindings",
    )

    sync_external_transform_context = fields.Char(
        string="Transform context",
        help="selection_add value for sync.data.transform.context_name"
        " (enables a custom transform context, e.g. 'QC-CONSTRUCTION -"
        " update')",
    )
    sync_external_transform_context_label = fields.Char(
        string="Transform context label",
        help="Human label for the transform context selection",
    )
    sync_external_no_match_json = fields.Text(
        string="No-match default (JSON)",
        help="default_option_no_match JSON set by _compute_context_name for"
        ' this context, e.g. {"ignore_associate": true}',
    )
    sync_external_enable_cron = fields.Boolean(
        string="Generate link cron",
        help="Emit a data/ir_cron.xml that links mirror rows to their target",
    )
    sync_external_cron_interval_number = fields.Integer(default=1)
    sync_external_cron_interval_type = fields.Selection(
        selection=[
            ("minutes", "Minutes"),
            ("hours", "Hours"),
            ("days", "Days"),
            ("weeks", "Weeks"),
            ("months", "Months"),
        ],
        default="days",
    )
    sync_external_cron_code = fields.Text(
        string="Cron code",
        help="Python body for the link cron (state=code). Empty = a TODO"
        " scaffold following the safirh key-chaining pattern.",
    )
    sync_external_enable_queue_job = fields.Boolean(
        string="Generate queue_job worker stub",
        help="Emit a queue_job worker stub + add queue_job to the generated"
        " module dependencies",
    )

    @api.depends("sync_external_file_type")
    def _compute_index_line_header(self):
        for rec in self:
            rec.sync_external_index_line_header = (
                0 if rec.sync_external_file_type == "csv" else 1
            )

    def build_sync_external_metadata(self):
        """Return the spreadsheet_extraction_metadata dict for this model.

        Pure builder (no DB writes / no I/O) so it is unit-testable; the
        code generator writer serializes the result into data/sync_model.xml.
        """
        self.ensure_one()
        header = []
        sync = []
        for field_id in self.field_ids:
            if field_id.name in self.IGNORE_SYNC_FIELD_NAME:
                continue
            label = (
                field_id.sync_external_associate_header_name
                or field_id.name.title()
            )
            entry = [label, field_id.name]
            if field_id.sync_external_value_map:
                try:
                    entry.append(json.loads(field_id.sync_external_value_map))
                except (ValueError, TypeError):
                    _logger.warning(
                        "Invalid sync_external_value_map JSON on field %s",
                        field_id.name,
                    )
            header.append(entry)
            if field_id.sync_external_is_primary:
                sync.append(field_id.name)
        if not sync:
            first = self.field_ids.filtered(
                lambda f: f.name not in self.IGNORE_SYNC_FIELD_NAME
            )[:1]
            sync = first.mapped("name")
        metadata = {
            "index_line_header": self.sync_external_index_line_header,
            "nb_line_header": self.sync_external_nb_line_header or 1,
            "header": header,
            "ignore_validation_header": False,
            "ignore_data": [
                line.strip()
                for line in (self.sync_external_ignore_data or "").splitlines()
                if line.strip()
            ],
            "filetype": self.sync_external_file_type,
            "bind": [
                bind._build_bind_config()
                for bind in self.sync_external_bind_ids
            ],
            "sync": sync,
        }
        if self.sync_external_file_type == "xlsx":
            metadata["sheet_name"] = self.sync_external_sheet_name or ""
        return metadata

    def build_sync_external_transform_py(self):
        """Render models/sync_data_transform.py source for these models, or ''.

        Aggregates over the recordset: a context_name selection_add (+ a
        _compute_context_name no-match override) per configured context, a stub
        for every method_call bind, and an optional queue_job worker stub.
        Pure string builder (no I/O) so it is unit-testable; the writer
        write_file_str's the result into the generated module's models/.
        """
        contexts = []
        seen_ctx = set()
        methods = []
        seen_method = set()
        enable_queue = False
        for model in self:
            ctx = model.sync_external_transform_context
            if ctx and ctx not in seen_ctx:
                seen_ctx.add(ctx)
                contexts.append(
                    (
                        ctx,
                        model.sync_external_transform_context_label or ctx,
                        (model.sync_external_no_match_json or "").strip(),
                    )
                )
            for bind in model.sync_external_bind_ids:
                if bind.method_call and bind.method_call not in seen_method:
                    seen_method.add(bind.method_call)
                    methods.append(
                        (bind.method_call, model.name, bind.target_model)
                    )
            if model.sync_external_enable_queue_job:
                enable_queue = True
        if not (contexts or methods or enable_queue):
            return ""
        lines = [
            "# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)",
            "import logging",
            "",
            "from odoo import api, fields, models",
            "",
            "_logger = logging.getLogger(__name__)",
            "",
            "",
            "class SyncDataTransform(models.Model):",
            '    _inherit = "sync.data.transform"',
            "",
        ]
        if contexts:
            sel = ", ".join(f"({c!r}, {label!r})" for c, label, _ in contexts)
            ondel = ", ".join(f'{c!r}: "set null"' for c, _, _ in contexts)
            lines += [
                "    context_name = fields.Selection(",
                f"        selection_add=[{sel}],",
                f"        ondelete={{{ondel}}},",
                "    )",
                "",
                '    @api.depends("context_name")',
                "    def _compute_context_name(self):",
                "        super()._compute_context_name()",
                "        for rec in self:",
            ]
            for c, _, no_match in contexts:
                value = no_match or "{}"
                lines += [
                    f"            if rec.context_name == {c!r} and not"
                    " rec.default_option_no_match:",
                    f"                rec.default_option_no_match = {value!r}",
                ]
            lines += [""]
        if methods:
            # Shared staging helper: a method_call bind must route through
            # sync.data.transform.exec (the validation step), NOT create
            # directly. action_write_all() materializes the staged rows.
            lines += [
                "    def _stage_exec(self, vals):",
                '        """Stage one sync.data.transform.exec row on this'
                " transform.",
                "        action_write_all() materializes it later (resolving"
                " #REPLACE",
                "        parent->child dependencies) -- the validation step."
                '"""',
                '        vals.setdefault("sync_data_transform_id", self.id)',
                '        return self.env["sync.data.transform.exec"].create(',
                "            [vals]",
                "        )",
                "",
            ]
        for name, mirror, target in methods:
            target_value = target or "TODO.target.model"
            lines += [
                f"    def {name}(",
                "        self,",
                "        mirror_ids,",
                "        model_name,",
                "        bind_config,",
                "        bind_field_reverse,",
                "        metadata,",
                "        do_link=False,",
                "    ):",
                f'        """Stage {target} rows from {mirror} via'
                " sync.data.transform.exec",
                "        (validation step); action_write_all() applies them.",
                "",
                "        TODO map the mirror fields into modification_json"
                " (chain child",
                "        records through the parent row's id_depend_name"
                " #REPLACE token).",
                "        bind_config carries the bind metadata (e.g."
                " order_lines).",
                '        """',
                "        self.ensure_one()",
                "        for entry in mirror_ids:",
                "            self._stage_exec(",
                "                {",
                '                    "from_model_name": model_name,',
                '                    "from_id_ref": entry.id,',
                f'                    "to_model_name": {target_value!r},',
                '                    "method": "create",',
                "                    # TODO map mirror fields here:",
                '                    "modification_json": {},',
                "                }",
                "            )",
                f'        _logger.info("Staged %s {name} rows",'
                " len(mirror_ids))",
                "",
            ]
        if enable_queue:
            lines += [
                "    def _queue_transform_worker(self, record_id):",
                '        """TODO: per-record transform worker (runs via'
                " queue_job).",
                "        Dispatch from action_transform with"
                " self.delayable()._queue_transform_worker(rec).delay().",
                '        """',
                "        self.ensure_one()",
                "        return True",
                "",
            ]
        return "\n".join(lines) + "\n"

    def build_sync_external_cron_code(self):
        self.ensure_one()
        return self.sync_external_cron_code or DEFAULT_CRON_CODE_SCAFFOLD
