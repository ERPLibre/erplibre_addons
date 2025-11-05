# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import datetime
import logging
import os

from odoo import _, api, exceptions, fields, models, tools
from odoo.models import MAGIC_COLUMNS

_logger = logging.getLogger(__name__)
try:
    import odoorpc
except ImportError:  # pragma: no cover
    _logger.debug("Cannot import odoorpc")

MAGIC_FIELDS = MAGIC_COLUMNS + [
    "display_name",
    "__last_update",
    "access_url",
    "access_token",
    "access_warning",
    "activity_summary",
    "activity_ids",
    "message_follower_ids",
    "message_ids",
    "website_message_ids",
    "activity_type_id",
    "activity_user_id",
    "activity_state",
    "message_channel_ids",
    "message_main_attachment_id",
    "message_partner_ids",
    "activity_date_deadline",
    "message_attachment_count",
    "message_has_error",
    "message_has_error_counter",
    "message_is_follower",
    "message_needaction",
    "message_needaction_counter",
    "message_unread",
    "message_unread_counter",
]


class SyncDB(models.Model):
    _name = "sync.db"
    _inherit = "mail.thread"
    _description = "Sync odoo db"

    name = fields.Char(
        compute="_compute_name",
        store=True,
        help="Summary of this backup process",
    )

    protocol = fields.Selection(
        selection=[
            ("http", "http"),
            ("https", "https"),
        ],
        default="https",
        required=True,
    )

    method_sync = fields.Selection(
        selection=[
            ("all", "All"),
            # ("white", "White"),
        ],
        default="all",
        help=(
            "If empty, sync all field. If all, sync all not system and not"
            " compute field."
        ),
    )

    sync_host = fields.Char(
        string="Sync Server",
        help=(
            "The host name or IP address from your remote server. For example"
            " 192.168.0.1"
        ),
    )

    module_name = fields.Char(
        string="Module name",
        help="Separate by ; for multiple module check.",
    )

    sync_password = fields.Char(
        string="Password",
        help="The password for the SYNC connection.",
    )

    sync_port = fields.Integer(
        string="HTTP Port",
        help="The port for http or https",
        default=443,
    )

    database = fields.Char(
        string="Database",
        help="Database name, set nothing to get default database.",
    )

    sync_user = fields.Char(
        string="Username in the Sync Server",
        help=(
            "The username where the SYNC connection should be made with. This"
            " is the user on the external server."
        ),
    )

    sync_db_result_ids = fields.One2many(
        comodel_name="sync.db.result",
        inverse_name="sync_db_id",
        string="Sync DB Results",
    )

    @api.onchange("protocol")
    def _onchange_protocol(self):
        # update port
        if self.protocol == "http":
            self.sync_port = 80
        elif self.protocol == "https":
            self.sync_port = 443

    @api.depends(
        "protocol",
        "sync_user",
        "sync_host",
        "database",
        "sync_port",
        "module_name",
    )
    def _compute_name(self):
        """Get the right summary for this job."""
        for rec in self:
            rec.name = (
                f"{rec.protocol}://{rec.sync_host}:{rec.sync_port} with"
                f" '{rec.sync_user}' DB '{rec.database}' MOD"
                f" '{rec.module_name}'"
            )

    def action_sync_test_connection(self):
        error = ""
        for rec in self:
            try:
                if rec.protocol == "https":
                    odoo = odoorpc.ODOO(
                        rec.sync_host,
                        protocol="jsonrpc+ssl",
                        port=rec.sync_port,
                    )
                else:
                    odoo = odoorpc.ODOO(
                        rec.sync_host, protocol="jsonrpc", port=rec.sync_port
                    )
                if not odoo.version:
                    error = "Cannot extract Odoo version"
            except Exception:
                error = _("Cannot connect")
        if error:
            _logger.error("Error sync connexion test")
            raise exceptions.Warning(_("FAILED - Sync connexion : ") + error)
        else:
            _logger.info("Succeed sync connexion test")
            raise exceptions.Warning(_("SUCCEED - Sync connexion"))

    def get_odoo(self, rec):
        if rec.protocol == "https":
            odoo = odoorpc.ODOO(
                rec.sync_host, protocol="jsonrpc+ssl", port=rec.sync_port
            )
        else:
            odoo = odoorpc.ODOO(
                rec.sync_host, protocol="jsonrpc", port=rec.sync_port
            )
        db_list = odoo.db.list()
        if not db_list:
            raise exceptions.Warning(
                _("The server {} has not database.").format(self.sync_host)
            )
        db = rec.database
        if not db:
            if len(db_list) == 1:
                db = db_list[0]
            else:
                raise exceptions.Warning(
                    _("Please specify the database to sync.")
                )
        elif db not in db_list:
            raise exceptions.Warning(
                _("The server {} has not database named {}.").format(
                    self.sync_host, db
                )
            )

        try:
            odoo.login(db, rec.sync_user, rec.sync_password)
        except Exception:
            raise exceptions.Warning(
                _(
                    "FAILED - wrong credentials, is it good user name or"
                    " password?"
                )
            )
        return odoo

    def action_sync(self):
        """Run selected sync."""
        for rec in self:
            # action_sync_test_connection()
            odoo = self.get_odoo(rec)
            lst_field_ignore = []
            sync_field_type = "all"
            # all, all fields except system field
            # white, only list of field is synced
            # black, all item from list is ignored

            # List of item for specified model
            model_kwargs = {}
            # fields_value = model_value.get("fields", {})
            # if fields_value.get("type") == "all":
            #     pass
            # elif fields_value.get("type") == "white":
            #     model_kwargs = {"fields": fields_value.get("lst")}
            # elif fields_value.get("type") == "black":
            #     # TODO
            #     pass
            # else:
            #     # TODO, by default, all
            #     pass

            rec.sync_db_result_ids = [(5,)]
            lst_existing_result = []
            # Validate module
            if rec.module_name:
                # Unique list and format it
                lst_module_name = list(
                    set([a.strip() for a in rec.module_name.split(";")])
                )
                for module_name in lst_module_name:
                    self._process_module(
                        rec,
                        module_name,
                        model_kwargs,
                        odoo,
                        lst_existing_result,
                    )

    def _process_module(
        self, rec, module_name, model_kwargs, odoo, lst_existing_result
    ):
        dct_model = {}
        local_module = (
            self.env["ir.module.module"]
            .search([("name", "=", module_name)])
            .exists()
        )
        if not local_module:
            self.env["sync.db.result"].create(
                {
                    "sync_db_id": rec.id,
                    "type_result": "missing_module",
                    "source": "local",
                    "sequence": 1,
                    "msg": f"Missing module '{module_name}'",
                    "data": module_name,
                    "resolution": "solution_local",
                    "status": "error",
                }
            )
        else:
            if (
                not model_kwargs
                and rec.method_sync
                and rec.method_sync == "all"
                and local_module
            ):
                all_model = [
                    a.res_id
                    for a in self.env["ir.model.data"].search(
                        [
                            (
                                "module",
                                "in",
                                [a.name for a in local_module],
                            ),
                            ("model", "=", "ir.model.fields"),
                        ]
                    )
                ]
                lst_all_fields = []
                all_fields = self.env["ir.model.fields"].search(
                    [
                        # ("model_id", "in", all_model),
                        ("id", "in", all_model),
                        ("name", "not in", MAGIC_FIELDS),
                    ]
                )
                for field_id in all_fields:
                    # remove field type compute
                    if (
                        not self.env[field_id.model]
                        ._fields.get(field_id.name)
                        .compute
                    ):
                        lst_all_fields.append(field_id)
                        if field_id.model in dct_model.keys():
                            lst_field_to_add = dct_model[field_id.model][
                                "fields"
                            ]["lst"]
                            lst_field_to_add.append(field_id.name)
                        else:
                            dct_model[field_id.model] = {
                                "fields": {
                                    "type": "white",
                                    "lst": [field_id.name],
                                }
                            }

        remote_module_ids = odoo.env["ir.module.module"].search(
            [("name", "=", module_name)]
        )
        if not remote_module_ids:
            self.env["sync.db.result"].create(
                {
                    "sync_db_id": rec.id,
                    "type_result": "missing_module",
                    "source": "remote",
                    "sequence": 1,
                    "msg": f"Missing module '{module_name}'",
                    "data": module_name,
                    "resolution": "solution_remote",
                    "status": "warning",
                }
            )
        if not remote_module_ids or not local_module:
            # Ignore, module not existing
            return
        remote_module_id = remote_module_ids[0]
        remote_module = odoo.env["ir.module.module"].browse(remote_module_id)
        if remote_module.state != "installed":
            # TODO validate can be install
            self.env["sync.db.result"].create(
                {
                    "sync_db_id": rec.id,
                    "type_result": "module_not_installed",
                    "source": "remote",
                    "sequence": 1,
                    "msg": f"Module '{module_name}' not installed",
                    "data": module_name,
                    "resolution": "solution_remote",
                    "status": "warning",
                }
            )
        elif local_module.latest_version != remote_module.latest_version:
            need_update = (
                local_module.installed_version
                == remote_module.installed_version
            )
            value = {
                "sync_db_id": rec.id,
                "type_result": "module_wrong_version",
                "sequence": 2,
                "status": "warning",
                "msg": (
                    f"Module '{module_name}', local version"
                    f" '{local_module.latest_version}', remote"
                    " version"
                    f" '{remote_module.latest_version}'"
                ),
                "data": module_name,
            }
            if need_update:
                value["resolution"] = "solution_remote"
            self.env["sync.db.result"].create(value)

        # Validate model
        for model_name, model_value in dct_model.items():
            if model_name not in odoo.env:
                key = (
                    f"model_name {model_name} type_result"
                    " missing_model source remote"
                )
                if key not in lst_existing_result:
                    lst_existing_result.append(key)
                    self.env["sync.db.result"].create(
                        {
                            "sync_db_id": rec.id,
                            "model_name": model_name,
                            "type_result": "missing_model",
                            "source": "remote",
                            "status": "error",
                            "sequence": 1,
                        }
                    )
                continue

            v = odoo.env[model_name].search([])
            try:
                lst_v = odoo.execute_kw(model_name, "read", [v], model_kwargs)
            except Exception as e:
                self.env["sync.db.result"].create(
                    {
                        "sync_db_id": rec.id,
                        "model_name": model_name,
                        "type_result": "missing_field",
                        "source": "remote",
                        "sequence": 1,
                        "msg": e,
                        "status": "error",
                    }
                )
                lst_v = []

            for v_item in lst_v:
                # Compare with id by default
                local_item = (
                    self.env[model_name].browse(v_item.get("id")).exists()
                )
                if not local_item:
                    self.env["sync.db.result"].create(
                        {
                            "sync_db_id": rec.id,
                            "model_name": model_name,
                            # "field_value_remote": (
                            #     f"id '{v_item.get('id')}' name"
                            #     f" '{v_item.get('display_name')}'"
                            # ),
                            "record_id": v_item.get("id"),
                            "type_result": "missing_result",
                            "data": {
                                a: v
                                if type(v) is not list
                                else (v[0] if len(v) else [])
                                for a, v in v_item.items()
                                if a not in MAGIC_FIELDS
                            },
                            "source": "local",
                            "resolution": "solution_local",
                        }
                    )
                else:
                    lst_field = model_value.get("fields", {}).get("lst")
                    for field_name in lst_field:
                        if hasattr(local_item, field_name):
                            local_value = getattr(local_item, field_name)
                            if type(local_value) in (
                                datetime.datetime,
                                datetime.date,
                            ):
                                local_value = str(local_value)

                            remote_value = v_item.get(field_name)
                            field_type = (
                                self.env[model_name]
                                ._fields.get(field_name)
                                .type
                            )

                            if field_type == "one2many":
                                continue

                            if field_type == "many2one":
                                remote_value_transformed = (
                                    remote_value[0] if remote_value else False
                                )
                                if remote_value_transformed != local_value.id:
                                    self.env["sync.db.result"].create(
                                        {
                                            "sync_db_id": rec.id,
                                            "model_name": model_name,
                                            "field_name": field_name,
                                            "record_id": v_item.get("id"),
                                            "field_value_local": local_value.id,
                                            "field_value_remote": remote_value,
                                            "type_result": "diff_value",
                                            "resolution": (
                                                "solution_remote_local"
                                            ),
                                        }
                                    )
                            elif field_type in (
                                "one2many",
                                "many2many",
                            ):
                                remote_value_transformed = (
                                    remote_value if remote_value else []
                                )
                                if remote_value_transformed != local_value.ids:
                                    self.env["sync.db.result"].create(
                                        {
                                            "sync_db_id": rec.id,
                                            "model_name": model_name,
                                            "field_name": field_name,
                                            "field_value_local": local_value.ids,
                                            "record_id": v_item.get("id"),
                                            "field_value_remote": remote_value,
                                            "type_result": "diff_value",
                                            "resolution": (
                                                "solution_remote_local"
                                            ),
                                        }
                                    )
                            elif local_value != remote_value:
                                self.env["sync.db.result"].create(
                                    {
                                        "sync_db_id": rec.id,
                                        "model_name": model_name,
                                        "field_name": field_name,
                                        "record_id": v_item.get("id"),
                                        "field_value_local": local_value,
                                        "field_value_remote": remote_value,
                                        "type_result": "diff_value",
                                        "resolution": "solution_remote_local",
                                        "msg": (
                                            "Different value, local"
                                            f" '{local_item}', remote"
                                            f" '{remote_value}'"
                                        ),
                                    }
                                )
                        else:
                            key = (
                                "model_name"
                                f" {model_name} type_result"
                                " missing_field source local"
                                f" field_name {field_name}"
                            )
                            if key not in lst_existing_result:
                                lst_existing_result.append(key)
                                self.env["sync.db.result"].create(
                                    {
                                        "sync_db_id": rec.id,
                                        "model_name": model_name,
                                        "type_result": "missing_field",
                                        "source": "local",
                                        "field_name": field_name,
                                        "sequence": 1,
                                        "msg": (
                                            "Missing field"
                                            f" '{field_name}' to"
                                            " local instance."
                                        ),
                                        "status": "error",
                                    }
                                )

            lst_v_local = self.env[model_name].search([])
            for v_item in lst_v_local:
                gen = (x for x in lst_v if x.get("id") == v_item.id)
                v_remote = next(gen, None)
                # No need to compare, already compared
                if not v_remote:
                    data = {}
                    lst_field = model_value.get("fields", {}).get("lst")
                    for field_name in lst_field:
                        field_type = (
                            self.env[model_name]._fields.get(field_name).type
                        )
                        if field_type == "one2many":
                            continue

                        v = getattr(v_item, field_name)
                        if field_type == "many2one":
                            if v.id:
                                data[field_name] = v.id
                        elif field_type in ("date", "datetime"):
                            data[field_name] = (
                                str(v) if v is not False else False
                            )
                        elif field_type in ("one2many", "many2many"):
                            if v:
                                data[field_name] = [(6, 0, v.ids)]
                            # if not v:
                            #     msg[field_name] = [(5,)]
                            # else:
                            #     msg[field_name] = [(6, 0, v.ids)]
                        elif field_type in ("char", "html", "text"):
                            if v:
                                data[field_name] = v
                        elif field_type == "boolean":
                            data[field_name] = True if v else False
                        else:
                            # data[field_name] = v if v != "False" else False
                            data[field_name] = v

                    self.env["sync.db.result"].create(
                        {
                            "sync_db_id": rec.id,
                            "model_name": model_name,
                            # "field_value_local": (
                            #     f"id '{v_item.id}' name"
                            #     f" '{v_item.display_name}'"
                            # ),
                            "record_id": v_item.id,
                            "type_result": "missing_result",
                            "data": data,
                            "source": "remote",
                            "resolution": "solution_remote",
                        }
                    )
