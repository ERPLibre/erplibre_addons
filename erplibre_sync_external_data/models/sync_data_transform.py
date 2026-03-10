import hashlib
import json
import logging

from odoo import _, api, conf, fields, models

_logger = logging.getLogger(__name__)


class SyncDataTransform(models.Model):
    _name = "sync.data.transform"
    _description = "sync_data_transform"
    _inherit = ["mail.activity.mixin", "mail.thread"]

    name = fields.Char(tracking=True, compute="_compute_name", store=True)

    context_name = fields.Selection(
        selection=[("default", "Default")],
        string="Context name",
        tracking=True,
    )

    time_execution_transform_start = fields.Datetime(
        string="Execution transform start", tracking=True, readonly=True
    )

    time_execution_transform_end = fields.Datetime(
        string="Execution transform end", tracking=True, readonly=True
    )

    time_duration_extract = fields.Float(
        compute="_compute_time_duration_extract", store=True, tracking=True
    )

    time_duration_extract_fr = fields.Char(
        compute="_compute_time_duration_extract", store=True, tracking=True
    )

    sync_data_transform_exec_ids = fields.One2many(
        comodel_name="sync.data.transform.exec",
        inverse_name="sync_data_transform_id",
    )

    sync_data_transform_exec_count = fields.Integer(
        compute="_compute_sync_data_transform_exec_count"
    )

    do_update = fields.Boolean(
        help="If True, will create or update record, else running into dry mode."
    )

    enable_default_option_no_match = fields.Boolean()

    default_option_no_match = fields.Text(
        default="", compute="_compute_context_name", store=True, readonly=False
    )

    is_transforming = fields.Boolean(help="Will be true if run in queue")

    has_data_to_write = fields.Boolean(compute="_compute_has_data_to_write")

    data_was_wrote = fields.Boolean(help="Will disable has_data_to_write")

    sync_model_ids = fields.Many2many(
        "sync.model",
        string="Template sync",
        tracking=True,
    )

    @api.depends("context_name")
    def _compute_context_name(self):
        pass

    @api.depends("sync_data_transform_exec_ids", "data_was_wrote")
    def _compute_has_data_to_write(self):
        for rec in self:
            rec.has_data_to_write = (
                bool(rec.sync_data_transform_exec_ids)
                and not rec.data_was_wrote
            )

    mail_activity_default_user_id = fields.Many2one(
        comodel_name="res.users",
        string="User",
    )

    mail_activity_ids = fields.Many2many(comodel_name="mail.activity")

    mail_activity_count = fields.Integer(
        compute="_compute_mail_activity_count"
    )

    filter_search_ids = fields.Many2many(
        comodel_name="sync.data.transform.filter_search",
        default=lambda self: self.env["sync.data.transform.filter_search"]
        .search([])
        .ids,
    )

    def action_open_transform_exec(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Transformation exec",
            "res_model": "sync.data.transform.exec",
            "view_mode": "list",
            "view_id": self.env.ref(
                "erplibre_sync_external_data.sync_data_transform_exec_view_list_edit_inline"
            ).id,
            "domain": [("sync_data_transform_id", "=", self.id)],
            "context": {
                "default_sync_data_transform_id": self.id,
            },
        }

    @api.depends("sync_data_transform_exec_ids")
    def _compute_sync_data_transform_exec_count(self):
        for rec in self:
            rec.sync_data_transform_exec_count = len(
                rec.sync_data_transform_exec_ids
            )

    @api.depends("context_name")
    def _compute_name(self):
        for rec in self:
            rec.name = rec.context_name or ""

    @api.depends("mail_activity_ids")
    def _compute_mail_activity_count(self):
        for rec in self:
            rec.mail_activity_count = len(rec.mail_activity_ids)

    def action_link(self, ctx=None):
        self.action_transform_algo(ctx=ctx, do_link=True)

    def action_write_all(self, ctx=None):
        for rec in self:
            rec.sync_data_transform_exec_ids.action_write_modification()
            rec.data_was_wrote = True

    def action_transform_algo(self, ctx=None, do_link=False):
        self._set_start_execution_time()
        if "queue_job" in conf.server_wide_modules:
            self.with_delay().action_transform(ctx=ctx, do_link=do_link)
            self.is_transforming = True
            status = {}
        else:
            status = self.action_transform(ctx=ctx, do_link=do_link)
            self._set_end_execution_time()
        return status

    def _set_end_execution_time(self, force=False):
        for rec in self:
            if not rec.time_execution_transform_end or force:
                rec.time_execution_transform_end = fields.Datetime.now()

    def _set_start_execution_time(self):
        for rec in self:
            if not rec.time_execution_transform_start:
                rec.time_execution_transform_start = fields.Datetime.now()

    def action_transform(self, ctx=None, do_link=False):
        for rec in self:
            if rec.context_name != "default":
                continue
            rec.action_transform_default(rec.sync_model_ids, do_link)
        return {}

    def action_transform_default(self, sync_model_ids, do_link):
        for rec in self:
            sync_data_exec_id = self.env["sync.data.exec"].search(
                [("transform_id", "=", rec.id)], limit=1
            )
            for sync_model_id in sync_model_ids:
                _logger.info(sync_model_id.model_name)
                metadata = sync_model_id.spreadsheet_extraction_metadata
                if not metadata:
                    continue
                metadata = json.loads(metadata)
                bindings = metadata.get("bind")
                if not bindings:
                    continue

                for bind_config in bindings:
                    ignore = bind_config.get("ignore")
                    if ignore:
                        continue
                    link_only = bind_config.get("link_only")
                    if link_only and not do_link:
                        continue
                    bind_field_reverse = bind_config.get("bind_field_reverse")
                    if not bind_field_reverse:
                        continue

                    created_ids = [
                        a.res_id
                        for a in sync_data_exec_id.sync_data_create_ids
                        if a.res_model == sync_model_id.model_name
                    ]
                    sync_model_mirror_create_ids = self.env[
                        sync_model_id.model_name
                    ].browse(created_ids)

                    method_call = bind_config.get("method_call")
                    if not method_call:
                        cb = rec.update_bind_transform
                    else:
                        cb = getattr(rec, method_call)
                    cb(
                        sync_model_mirror_create_ids,
                        sync_model_id.model_name,
                        bind_config,
                        bind_field_reverse,
                        do_link=link_only,
                        do_update=rec.do_update,
                    )

    def update_bind_transform(
        self,
        mirror_ids,
        model_name,
        bind_config,
        bind_field_reverse,
        do_link=False,
        do_update=False,
    ):
        transform_exec_batch = []

        bind_field_model = bind_config.get("bind_field_model")
        if not bind_field_model:
            return

        for model_key, bind_model_config in bind_field_model.items():
            bind_fields = bind_model_config.get("bindings")

            if not bind_fields:
                return
            default_fields = bind_model_config.get("default_field", {})

            bind_condition = bind_config.get("bind_condition")
            if bind_condition:
                mirror_ids = mirror_ids.search(bind_condition)

            bind_group_by = bind_config.get("bind_group_by")
            if bind_group_by:
                mirror_groups = mirror_ids.grouped(bind_group_by[0])
            else:
                mirror_groups = {None: mirror_ids}

            for rec in self:
                model_field_name = bind_fields[0][0]
                model_sync_name = bind_fields[0][1]
                for key, search_values in mirror_groups.items():
                    for mirror_id in search_values:
                        model_value = {}
                        project_number = getattr(mirror_id, model_sync_name)
                        if not project_number:
                            continue
                        # Support model
                        model_id = self.env[model_key].search(
                            [
                                (
                                    model_field_name,
                                    "=",
                                    project_number,
                                )
                            ]
                        )

                        # TODO option to create directly data without transformation
                        if not do_link:
                            transform_depends, dependency_links = (
                                rec._bind_transform(
                                    bind_fields,
                                    mirror_id,
                                    model_key,
                                    model_value,
                                    default_fields,
                                )
                            )
                            rec._bind_transform_model(
                                project_number,
                                mirror_id,
                                model_id,
                                model_name,
                                model_value,
                                transform_depends,
                                model_key,
                                dependency_links,
                                bind_field_reverse,
                                transform_exec_batch,
                            )

                        need_link = getattr(mirror_id, bind_field_reverse)
                        if not need_link and model_id:
                            mirror_id.write({bind_field_reverse: model_id})

        if transform_exec_batch:
            self.env["sync.data.transform.exec"].create(transform_exec_batch)

    def _bind_transform(
        self,
        bind_fields,
        mirror_id,
        model_key,
        model_value,
        default_fields,
    ):
        self.ensure_one()
        transform_depends = []
        dependency_links = []
        for set_bind in bind_fields:
            field_name_target = set_bind[0]
            field_name_mirror = set_bind[1]
            target_field = self.env[model_key]._fields.get(field_name_target)
            if not target_field:
                raise ValueError(
                    f"Cannot find field '{field_name_target}' into model '{model_key}'."
                )
            value = getattr(mirror_id, field_name_mirror)
            ttype = target_field.type
            update_value = None

            if ttype == "many2one":
                rec_name = self.env[model_key]._rec_name
                found = self.env[model_key].search([(rec_name, "=", value)])
                if found:
                    update_value = found.id
                else:
                    associate_model = target_field.comodel_name
                    associate_key = (
                        f"{associate_model}.create.{rec_name}.{value}"
                    )
                    parent_exec = self.env["sync.data.transform.exec"].search(
                        [("associate_key", "=", associate_key)]
                    )
                    if not parent_exec:
                        update_value = 0
                    else:
                        update_value = parent_exec.id_depend_name
                        dependency_links.append((4, parent_exec.id))
            elif ttype in ("many2many", "one2many"):
                _logger.warning(
                    "many2many/one2many binding not yet implemented for field '%s'",
                    field_name_target,
                )
            else:
                update_value = value
            if update_value:
                model_value[field_name_target] = update_value
        for key, value in default_fields.items():
            # Support magic value with computing
            ttype = self.env[model_key]._fields.get(key)
            if ttype.type in ("many2one", "many2many", "one2many"):
                if ttype.type != "many2one":
                    _logger.warning(
                        "many2many/one2many default field not fully implemented for field '%s'",
                        key,
                    )
                related_model = self.env[ttype.base_field.comodel_name]
                values_to_insert = []
                search_values = value if isinstance(value, list) else [value]
                for vvalue in search_values:
                    if isinstance(vvalue, dict):
                        search_name = vvalue.get(related_model._rec_name)
                    else:
                        search_name = vvalue
                    value_id = related_model.search(
                        [(related_model._rec_name, "=", search_name)]
                    )
                    if not value_id:
                        if isinstance(vvalue, dict):
                            modification_value = vvalue
                        else:
                            modification_value = {
                                related_model._rec_name: vvalue
                            }
                        modification_json = json.dumps(modification_value)

                        associate_key = f"{ttype.base_field.comodel_name}.create.{related_model._rec_name}.{search_name}"
                        note = "Create bind_field_model sub transform"
                        self._add_transform(
                            ttype.base_field.comodel_name,
                            model_key,
                            modification_json,
                            associate_key,
                            dependency_links,
                            transform_depends,
                            note,
                            ttype,
                            values_to_insert,
                            model_value,
                            key,
                        )
                    else:
                        if ttype.type == "many2many":
                            for value_id_id in value_id:
                                values_to_insert.append((4, value_id_id.id))
                        elif ttype.type == "many2one":
                            model_value[key] = value_id.id
                        elif ttype.type == "one2many":
                            _logger.warning(
                                "one2many write-back not yet implemented"
                            )
                        else:
                            model_value[key] = value_id
                if values_to_insert:
                    model_value[key] = values_to_insert
            else:
                model_value[key] = value

        return transform_depends, dependency_links

    def _add_transform(
        self,
        to_model_name,
        from_model_name,
        modification_json,
        associate_key,
        dependency_links,
        transform_depends,
        note,
        ttype=None,
        values_to_insert=None,
        model_value=None,
        key=None,
        mode_b=False,
    ):
        transform_exec_values = {
            "to_model_name": to_model_name,
            "sync_data_transform_id": self.id,
            "from_model_name": from_model_name,
            "note": note,
            "modification": modification_json,
            "method": "create",
            "associate_key": associate_key,
        }
        if dependency_links:
            transform_exec_values["depend_ids"] = dependency_links

        hash_transform = hashlib.sha256(
            json.dumps(transform_exec_values).encode()
        ).hexdigest()
        transform_exec_id = self.env["sync.data.transform.exec"].search(
            [
                "|",
                (
                    "hash_generic_value",
                    "=",
                    hash_transform,
                ),
                (
                    "associate_key",
                    "=",
                    associate_key,
                ),
            ],
            limit=1,
        )

        if not transform_exec_id:
            # TODO need for all?
            if transform_depends and mode_b:
                transform_exec_values["depend_ids"] = [
                    (6, 0, transform_depends)
                ]
            transform_exec_values["hash_generic_value"] = hash_transform
            transform_exec_id = self.env["sync.data.transform.exec"].create(
                [transform_exec_values]
            )

        if not mode_b:
            replace_key = transform_exec_id.id_depend_name

            transform_depends.append(transform_exec_id.id)

            if ttype.type == "many2many":
                values_to_insert.append((4, replace_key))
            elif ttype.type == "many2one":
                model_value[key] = replace_key
            elif ttype.type == "one2many":
                _logger.warning(
                    "one2many not yet implemented in _add_transform"
                )
        return transform_exec_id

    def _bind_transform_model(
        self,
        project_number,
        mirror_id,
        model_id,
        model_name,
        model_value,
        transform_depends,
        model_key,
        dependency_links,
        bind_field_reverse,
        transform_exec_batch,
    ):
        self.ensure_one()
        record_name = str(project_number)
        if not model_id:
            model_value[model_id._rec_name] = record_name

            modification_json = json.dumps(model_value)
            transform_depends = list(set(transform_depends))
            associate_key = (
                f"{model_key}.create.{model_id._rec_name}.{record_name}"
            )
            note = "Create bind_field_model"
            transform_exec_id = self._add_transform(
                model_key,
                model_name,
                modification_json,
                associate_key,
                dependency_links,
                transform_depends,
                note,
                mode_b=True,
            )

            modification_json = json.dumps(
                {bind_field_reverse: transform_exec_id.id_depend_name}
            )
            transform_exec_batch.append(
                {
                    "to_model_name": model_name,
                    "to_id_ref": mirror_id.id,
                    "sync_data_transform_id": self.id,
                    "from_id_ref": model_id.id,
                    "from_model_name": model_key,
                    "depend_ids": [(6, 0, transform_exec_id.ids)],
                    "modification": modification_json,
                    "method": "write",
                }
            )
        else:
            _logger.info(
                "Model update for '%s' - skipped (not yet implemented)",
                project_number,
            )

    @api.depends(
        "time_execution_transform_start", "time_execution_transform_end"
    )
    def _compute_time_duration_extract(self):
        sync_data_exec = self.env["sync.data.exec"]
        for rec in self:
            duration, label = sync_data_exec._compute_duration(
                rec.time_execution_transform_start,
                rec.time_execution_transform_end,
            )
            if (
                not rec.time_execution_transform_start
                and rec.time_execution_transform_end
            ):
                rec.time_execution_transform_start = (
                    rec.time_execution_transform_end
                )
            rec.time_duration_extract = duration
            rec.time_duration_extract_fr = label
