#!/usr/bin/env python3
# © 2021-2025 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
import json
import os

from lxml import etree as ET
from lxml.builder import E
from odoo import api, fields, models
from odoo.addons.code_generator import code_generator_data

BREAK_LINE_OFF = "\n"
XML_VERSION_HEADER = '<?xml version="1.0" encoding="utf-8"?>' + BREAK_LINE_OFF


class CodeGeneratorWriter(models.Model):
    _inherit = "code.generator.writer"

    def set_xml_data_file(self, module):
        super(CodeGeneratorWriter, self).set_xml_data_file(module)

        if not module.enable_sync_external_data_write:
            return

        cg_data = code_generator_data.get_code_generator_data(self.env)

        lst_record_xml = []
        for devops_cg_model_id in module.devops_cg_model_ids:
            if not devops_cg_model_id.enable_sync_external:
                continue
            model_name_underscore = devops_cg_model_id.name.replace(".", "_")
            lst_field = []

            lst_field.append(E.field({"name": "name"}, model_name_underscore))
            lst_field.append(
                E.field({"name": "model_name"}, devops_cg_model_id.name)
            )
            if devops_cg_model_id.sync_external_scenario:
                lst_field.append(
                    E.field(
                        {"name": "scenario"},
                        devops_cg_model_id.sync_external_scenario,
                    )
                )
            if devops_cg_model_id.sync_external_context_name:
                lst_field.append(
                    E.field(
                        {"name": "context_name"},
                        devops_cg_model_id.sync_external_context_name,
                    )
                )
            if devops_cg_model_id.sync_external_description:
                lst_field.append(
                    E.field(
                        {"name": "description"},
                        devops_cg_model_id.sync_external_description,
                    )
                )

            json_values = devops_cg_model_id.build_sync_external_metadata()
            json_data_str = json.dumps(json_values, indent=4)

            lst_field.append(ET.Comment(" prettier-ignore-start "))
            lst_field.append(
                E.field(
                    {"name": "spreadsheet_extraction_metadata"},
                    f"\n{json_data_str}\n",
                )
            )
            lst_field.append(ET.Comment(" prettier-ignore-end "))

            str_id = f"sync_model_{model_name_underscore}"
            record_xml = E.record(
                {"model": "sync.model", "id": str_id}, *lst_field
            )
            lst_record_xml.append(record_xml)

        odoo_data = {"noupdate": "1"}
        module_file = E.odoo(odoo_data, *lst_record_xml)
        data_file_path = os.path.join(cg_data.data_path, "sync_model.xml")
        result = XML_VERSION_HEADER.encode("utf-8") + ET.tostring(
            module_file, pretty_print=True
        )
        cg_data.write_file_binary(data_file_path, result, data_file=True)

        # data/ir_cron.xml — link cron(s)
        lst_cron_xml = []
        for devops_cg_model_id in module.devops_cg_model_ids:
            if not (
                devops_cg_model_id.enable_sync_external
                and devops_cg_model_id.sync_external_enable_cron
            ):
                continue
            model_name_underscore = devops_cg_model_id.name.replace(".", "_")
            cron_xml = E.record(
                {
                    "model": "ir.cron",
                    "id": f"cron_sync_{model_name_underscore}",
                },
                E.field(
                    {"name": "name"},
                    f"Sync link {devops_cg_model_id.name}",
                ),
                E.field(
                    {
                        "name": "model_id",
                        "ref": "erplibre_sync_external_data"
                        ".model_sync_data_exec",
                    }
                ),
                E.field({"name": "state"}, "code"),
                E.field(
                    {"name": "code"},
                    devops_cg_model_id.build_sync_external_cron_code(),
                ),
                E.field(
                    {"name": "interval_number"},
                    str(devops_cg_model_id.sync_external_cron_interval_number),
                ),
                E.field(
                    {"name": "interval_type"},
                    devops_cg_model_id.sync_external_cron_interval_type,
                ),
                E.field({"name": "user_id", "ref": "base.user_root"}),
            )
            lst_cron_xml.append(cron_xml)
        if lst_cron_xml:
            cron_file = E.odoo({}, *lst_cron_xml)
            cron_path = os.path.join(cg_data.data_path, "ir_cron.xml")
            cron_result = XML_VERSION_HEADER.encode("utf-8") + ET.tostring(
                cron_file, pretty_print=True
            )
            cg_data.write_file_binary(cron_path, cron_result, data_file=True)

    def set_module_python_file(self, module):
        super(CodeGeneratorWriter, self).set_module_python_file(module)
        if not module.enable_sync_external_data_write:
            return
        models = module.devops_cg_model_ids.filtered("enable_sync_external")
        source = models.build_sync_external_transform_py()
        if not source:
            return
        cg_data = code_generator_data.get_code_generator_data(self.env)
        cg_data.write_file_str(
            os.path.join(cg_data.models_path, "sync_data_transform.py"),
            source,
        )
