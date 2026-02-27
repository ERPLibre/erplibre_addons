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
IGNORE_FIELD_NAME = ["file_no_line", "company_currency_id"]


class CodeGeneratorWriter(models.Model):
    _inherit = "code.generator.writer"

    def set_xml_data_file(self, module):
        super(CodeGeneratorWriter, self).set_xml_data_file(module)

        if not module.enable_sync_external_data_write:
            return

        cg_data = code_generator_data.get_code_generator_data(self.env)

        # Add with template sync_data_exec.xml
        lst_record_xml = []
        for devops_cg_model_id in module.devops_cg_model_ids:
            if devops_cg_model_id.enable_sync_external:
                model_name_underscore = devops_cg_model_id.name.replace(
                    ".", "_"
                )
                lst_field = []

                # TODO get title of sentence of description
                field_xml = E.field({"name": "name"}, model_name_underscore)
                lst_field.append(field_xml)

                field_xml = E.field(
                    {"name": "model_name"}, devops_cg_model_id.name
                )
                lst_field.append(field_xml)

                field_xml = E.field({"name": "scenario"}, "TODO")
                lst_field.append(field_xml)

                field_xml = E.field({"name": "context_name"}, "TODO")
                lst_field.append(field_xml)

                lst_header = []
                for field_id in devops_cg_model_id.field_ids:
                    if field_id.name not in IGNORE_FIELD_NAME:
                        label_field = (
                            field_id.sync_external_associate_header_name
                        )
                        if not label_field:
                            label_field = field_id.name.title()
                        lst_header.append((label_field, field_id.name))

                json_values = {
                    "index_line_header": devops_cg_model_id.sync_external_index_line_header,
                    "header": lst_header,
                    "ignore_validation_header": False,
                    "ignore_data": [],
                    "filetype": devops_cg_model_id.sync_external_file_type,
                    "bind": [],
                }
                if devops_cg_model_id.field_ids:
                    json_values["sync"] = [
                        devops_cg_model_id.field_ids[0].name
                    ]
                if devops_cg_model_id.sync_external_file_type == "xlsx":
                    if devops_cg_model_id.sync_external_sheet_name:
                        json_values["sheet_name"] = (
                            devops_cg_model_id.sync_external_sheet_name
                        )
                    else:
                        json_values["sheet_name"] = ""

                json_data_str = json.dumps(json_values, indent=4)

                lst_field.append(ET.Comment(" prettier-ignore-start "))

                field_xml = E.field(
                    {"name": "spreadsheet_extraction_metadata"},
                    f"\n{json_data_str}\n",
                )
                lst_field.append(field_xml)

                lst_field.append(ET.Comment(" prettier-ignore-end "))

                # Create XML
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
