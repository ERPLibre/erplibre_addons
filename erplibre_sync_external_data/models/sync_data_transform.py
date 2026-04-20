import hashlib
import json
import logging
import os
from datetime import date, datetime

from odoo import _, api, conf, fields, models
from odoo.addons.queue_job.delay import chain, group

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
            if rec.sync_data_transform_exec_ids:
                rec.sync_data_transform_exec_count = len(
                    rec.sync_data_transform_exec_ids
                )
            else:
                rec.sync_data_transform_exec_count = 0

    @api.depends("context_name")
    def _compute_name(self):
        for rec in self:
            rec.name = ""
            if rec.context_name:
                rec.name = rec.context_name

    @api.depends("mail_activity_ids")
    def _compute_mail_activity_count(self):
        for rec in self:
            if rec.mail_activity_ids:
                rec.mail_activity_count = len(rec.mail_activity_ids)
            else:
                rec.mail_activity_count = 0

    def action_link(self, ctx=None):
        self.action_transform_algo(ctx=ctx, do_link=True)

    def action_write_all(self, ctx=None):
        for rec in self:
            rec.sync_data_transform_exec_ids.action_write_modification()
            rec.data_was_wrote = True

    def action_transform_algo(self, ctx=None, do_link=False):
        self._set_start_execution_time()
        if "queue_job" in conf.server_wide_modules:
            # chain(self.action_transform(ctx=ctx, do_link=do_link), self._set_end_execution_time())
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
        # status = super().action_transform(ctx=ctx, do_link=do_link)
        for rec in self:
            if not rec.context_name in [
                "default",
            ]:
                continue
            sync_model_ids = rec.sync_model_ids
            rec.action_transform_default(sync_model_ids, do_link)
        return {}

    def action_transform_default(self, sync_model_ids, do_link):
        for rec in self:
            sync_data_exec_id = self.env["sync.data.exec"].search(
                [("transform_id", "=", rec.id)], limit=1
            )
            # Doing project.project
            for sync_model_id in sync_model_ids:
                _logger.info(sync_model_id.model_name)
                metadata = sync_model_id.spreadsheet_extraction_metadata
                if not metadata:
                    continue
                metadata = json.loads(metadata)
                lst_bind = metadata.get("bind")
                if not lst_bind:
                    continue

                for dct_bind in lst_bind:
                    ignore = dct_bind.get("ignore")
                    if ignore:
                        continue
                    link_only = dct_bind.get("link_only")
                    if link_only and not do_link:
                        continue
                    bind_field_reverse = dct_bind.get("bind_field_reverse")
                    if not bind_field_reverse:
                        continue

                    # TODO support this when create (bind_field_reverse, "=", False), write (bind_field_reverse, "!=", False) sync_data_write_ids
                    sync_model_mirror_create_ids = self.env[
                        sync_model_id.model_name
                    ].search([(bind_field_reverse, "=", False)])

                    lst_id_sync_data_create = [
                        a.res_id
                        for a in sync_data_exec_id.sync_data_create_ids
                        if a.res_model == sync_model_id.model_name
                    ]
                    sync_model_mirror_create_ids = self.env[
                        sync_model_id.model_name
                    ].browse(lst_id_sync_data_create)

                    lst_id_sync_data_write = [
                        a.res_id
                        for a in sync_data_exec_id.sync_data_write_ids
                        if a.res_model == sync_model_id.model_name
                    ]
                    sync_model_mirror_write_ids = self.env[
                        sync_model_id.model_name
                    ].browse(lst_id_sync_data_write)

                    method_call = dct_bind.get("method_call")
                    if not method_call:
                        cb = rec.update_bind_transform
                    else:
                        cb = getattr(rec, method_call)
                    cb(
                        sync_model_mirror_create_ids,
                        sync_model_id.model_name,
                        dct_bind,
                        bind_field_reverse,
                        do_link=link_only,
                        do_update=rec.do_update,
                    )

    def update_bind_transform(
        self,
        mirror_ids,
        model_name,
        dct_bind,
        bind_field_reverse,
        do_link=False,
        do_update=False,
    ):
        lst_sync_data_transform_exec_value = []
        # crm_team_id = self.env["crm.team"].search(
        #     [("name", "=", CST_CRM_LEAD_TEAM)]
        # )

        dct_bind_field_model = dct_bind.get("bind_field_model")
        if not dct_bind_field_model:
            return

        for model_key, dct_bind_model in dct_bind_field_model.items():
            lst_bind_model = dct_bind_model.get("lst_bind")

            if not lst_bind_model:
                return
            dct_default_field = dct_bind_model.get("default_field", {})

            bind_condition = dct_bind.get("bind_condition")
            if bind_condition:
                mirror_ids = mirror_ids.search(bind_condition)

            bind_group_by = dct_bind.get("bind_group_by")
            if bind_group_by:
                dct_mirror_group = mirror_ids.grouped(bind_group_by[0])
            else:
                dct_mirror_group = {None: mirror_ids}

            for rec in self:
                model_field_name = lst_bind_model[0][0]
                model_sync_name = lst_bind_model[0][1]
                for key, lst_value in dct_mirror_group.items():
                    for mirror_id in lst_value:
                        model_value = {}
                        numero_projet = getattr(mirror_id, model_sync_name)
                        if not numero_projet:
                            continue
                        # Support model
                        model_id = self.env[model_key].search(
                            [
                                (
                                    model_field_name,
                                    "=",
                                    numero_projet,
                                )
                            ]
                        )

                        # TODO option to create directly data without transformation
                        if not do_link:
                            lst_transform_depend, lst_depends = (
                                rec._bind_transform(
                                    lst_bind_model,
                                    mirror_id,
                                    model_key,
                                    model_value,
                                    dct_default_field,
                                )
                            )
                            rec._bind_transform_model(
                                numero_projet,
                                mirror_id,
                                model_id,
                                model_name,
                                model_value,
                                lst_transform_depend,
                                model_key,
                                lst_depends,
                                bind_field_reverse,
                                lst_sync_data_transform_exec_value,
                            )

                        need_link = getattr(mirror_id, bind_field_reverse)
                        if not need_link and model_id:
                            mirror_id.write({bind_field_reverse: model_id})
                            # setattr(mirror_id, bind_field_reverse, model_id.id)

        if lst_sync_data_transform_exec_value:
            self.env["sync.data.transform.exec"].create(
                lst_sync_data_transform_exec_value
            )

    def _bind_transform(
        self,
        lst_bind_model,
        mirror_id,
        model_key,
        model_value,
        dct_default_field,
    ):
        self.ensure_one()
        lst_transform_depend = []
        lst_depends = []
        for set_bind in lst_bind_model:
            field_name_target = set_bind[0]
            field_name_mirror = set_bind[1]
            target_field = self.env[model_key]._fields.get(field_name_target)
            if not target_field:
                raise ValueError(
                    f"Cannot find field '{field_name_target}' into model '{model_key}'."
                )
            value = getattr(mirror_id, field_name_mirror)
            # Check target type, to change if got relation
            # ttype = mirror_id._fields.get(field_name_mirror).type
            ttype = target_field.type

            if ttype == "many2one":
                rec_name = self.env[model_key]._rec_name
                update_value = self.env[model_key].search(
                    [
                        (
                            rec_name,
                            "=",
                            value,
                        )
                    ]
                )
                if update_value:
                    update_value = update_value.id
                else:
                    # associate_model = model_key
                    associate_model = target_field.comodel_name
                    associate_key = (
                        f"{associate_model}.create.{rec_name}.{value}"
                    )
                    parent_sync_data_transform_exec_id = self.env[
                        "sync.data.transform.exec"
                    ].search(
                        [
                            (
                                "associate_key",
                                "=",
                                associate_key,
                            )
                        ]
                    )
                    if not parent_sync_data_transform_exec_id:
                        # TODO support creation transformation
                        modification_json = json.dumps({rec_name: value})
                        #
                        # transform_exec_values = {
                        #     "to_model_name": associate_model,
                        #     "sync_data_transform_id": self.id,
                        #     "from_model_name": model_key,
                        #     "note": "Create bind_field_model relation",
                        #     "modification": modification_json,
                        #     "method": "create",
                        #     "associate_key": associate_key,
                        # }
                        # lst_depends.append(
                        #     (
                        #         4,
                        #         parent_sync_data_transform_exec_id.id,
                        #     )
                        # )
                        # self._add_transform(
                        #     ttype.base_field.comodel_name,
                        #     model_key,
                        #     modification_json,
                        #     associate_key,
                        #     lst_depends,
                        #     lst_transform_depend,
                        #     ttype,
                        #     lst_value_insert,
                        #     model_value,
                        #     key,
                        # )
                        update_value = 0
                    else:
                        update_value = (
                            parent_sync_data_transform_exec_id.id_depend_name
                        )
                        lst_depends.append(
                            (
                                4,
                                parent_sync_data_transform_exec_id.id,
                            )
                        )
            elif ttype in ["many2many", "one2many"]:
                print("todo")
            else:
                update_value = value
            if update_value:
                model_value[field_name_target] = update_value
        for key, value in dct_default_field.items():
            # Support magic value with computing
            ttype = self.env[model_key]._fields.get(key)
            if ttype.type in ["many2one", "many2many", "one2many"]:
                if ttype.type in ["many2many", "one2many"]:
                    print("TODO")
                CLS_ttype = self.env[ttype.base_field.comodel_name]
                lst_value_insert = []
                if type(value) is list:
                    lst_value = value
                else:
                    lst_value = [value]
                for vvalue in lst_value:
                    if type(vvalue) is dict:
                        value_id = CLS_ttype.search(
                            [
                                (
                                    CLS_ttype._rec_name,
                                    "=",
                                    vvalue.get(CLS_ttype._rec_name),
                                )
                            ]
                        )
                    else:
                        value_id = CLS_ttype.search(
                            [
                                (
                                    CLS_ttype._rec_name,
                                    "=",
                                    vvalue,
                                )
                            ]
                        )
                    if not value_id:
                        if type(vvalue) is dict:
                            vvalue_name = vvalue.get(CLS_ttype._rec_name)
                            modification_value = vvalue
                        else:
                            modification_value = {CLS_ttype._rec_name: vvalue}
                            vvalue_name = vvalue
                        modification_json = json.dumps(modification_value)

                        associate_key = f"{ttype.base_field.comodel_name}.create.{CLS_ttype._rec_name}.{vvalue_name}"
                        note = "Create bind_field_model sub transform"
                        self._add_transform(
                            ttype.base_field.comodel_name,
                            model_key,
                            modification_json,
                            associate_key,
                            lst_depends,
                            lst_transform_depend,
                            note,
                            ttype,
                            lst_value_insert,
                            model_value,
                            key,
                        )
                    else:
                        if ttype.type in ["many2many"]:
                            for value_id_id in value_id:
                                lst_value_insert.append((4, value_id_id.id))
                        elif ttype.type in ["many2one"]:
                            model_value[key] = value_id.id
                        elif ttype.type in ["one2many"]:
                            print("todo")
                        else:
                            model_value[key] = value_id
                if lst_value_insert:
                    model_value[key] = lst_value_insert
            else:
                model_value[key] = value

        return lst_transform_depend, lst_depends

    def _add_transform(
        self,
        to_model_name,
        from_model_name,
        modification_json,
        associate_key,
        lst_depends,
        lst_transform_depend,
        note,
        ttype=None,
        lst_value_insert=None,
        model_value=None,
        key=None,
        mode_b=False,
    ):
        transform_exec_values = {
            "to_model_name": to_model_name,
            "sync_data_transform_id": self.id,
            # "from_id_ref": ticket_id.id,
            "from_model_name": from_model_name,
            "note": note,
            "modification": modification_json,
            "method": "create",
            "associate_key": associate_key,
        }
        if lst_depends:
            transform_exec_values["depend_ids"] = lst_depends

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
            if lst_transform_depend and mode_b:
                transform_exec_values["depend_ids"] = [
                    (6, 0, lst_transform_depend)
                ]
            transform_exec_values["hash_generic_value"] = hash_transform
            transform_exec_id = self.env["sync.data.transform.exec"].create(
                [transform_exec_values]
            )

        if not mode_b:
            replace_key = transform_exec_id.id_depend_name

            lst_transform_depend.append(transform_exec_id.id)

            if ttype.type in ["many2many"]:
                lst_value_insert.append((4, replace_key))
            elif ttype.type in ["many2one"]:
                # model_value[key] = value_id.id
                model_value[key] = replace_key
            elif ttype.type in ["one2many"]:
                print("TODO")
        return transform_exec_id

    def _bind_transform_model(
        self,
        numero_projet,
        mirror_id,
        model_id,
        model_name,
        model_value,
        lst_transform_depend,
        model_key,
        lst_depends,
        bind_field_reverse,
        lst_sync_data_transform_exec_value,
    ):
        self.ensure_one()
        record_name = f"{numero_projet}"
        # record_name = f"{numero_projet} {model_value.get(CST_model_model_FIELD_model_NUMBER)}"
        if not model_id:
            model_value[model_id._rec_name] = record_name

            modification_json = json.dumps(model_value)
            lst_transform_depend = list(set(lst_transform_depend))
            associate_key = (
                f"{model_key}.create.{model_id._rec_name}.{record_name}"
            )
            note = "Create bind_field_model"
            transform_exec_id = self._add_transform(
                model_key,
                model_name,
                modification_json,
                associate_key,
                lst_depends,
                lst_transform_depend,
                note,
                mode_b=True,
            )

            modification_json = json.dumps(
                {bind_field_reverse: transform_exec_id.id_depend_name}
            )
            lst_sync_data_transform_exec_value.append(
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
            # TODO update model
            print("update")

    @api.depends(
        "time_execution_transform_start", "time_execution_transform_end"
    )
    def _compute_time_duration_extract(self):
        for rec in self:
            if (
                not rec.time_execution_transform_start
                and not rec.time_execution_transform_end
            ):
                rec.time_duration_extract = 0
                rec.time_duration_extract_fr = _("Not running")
            elif (
                rec.time_execution_transform_start
                and not rec.time_execution_transform_end
            ):
                rec.time_duration_extract = 0
                rec.time_duration_extract_fr = _("Running")
            else:
                if (
                    not rec.time_execution_transform_start
                    and rec.time_execution_transform_end
                ):
                    # Strange case...
                    rec.time_execution_transform_start = (
                        rec.time_execution_transform_end
                    )
                if (
                    rec.time_execution_transform_end
                    < rec.time_execution_transform_start
                ):
                    duration_seconds = 0
                else:
                    delta = (
                        rec.time_execution_transform_end
                        - rec.time_execution_transform_start
                    )
                    duration_seconds = int(delta.total_seconds())

                rec.time_duration_extract = float(duration_seconds)
                rec.time_duration_extract_fr = self.env[
                    "sync.data.exec"
                ]._format_duration_fr(duration_seconds)
