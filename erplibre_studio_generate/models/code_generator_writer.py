# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""The code generator writer, narrowed to a studio project.

The writer exports everything it finds on the models of its module: the
SQL constraints, the access rights and record rules, the reports, the
actions and every view of the model. A studio module only extends models
that belong to other modules, so under the context key
``erplibre_studio_project_id`` the writer keeps the fields of the project
on the Python side and studio writes the views file itself.

The definition of a field of the project comes from the project, not from
``ir.model.fields``: once the generated module is installed, the database
row belongs to the module and keeps its former definition until the
module is upgraded.
"""

import os
import re

from lxml import etree
from odoo import models
from odoo.addons.code_generator import code_generator_data
from odoo.addons.erplibre_studio import arch as studio_arch
from odoo.addons.erplibre_studio.models.erplibre_studio_project import (
    STUDIO_PRIORITY,
)

VIEWS_FILE = "views/erplibre_studio_views.xml"

# Class attributes the writer copies from the extended model.
_COPIED_ATTRIBUTE = re.compile(r"^\s+_(order|rec_name) = .*$\n?", re.M)
# The import line of the writer; a studio model only declares fields.
_WRITER_IMPORT = re.compile(r"^from odoo import .*$", re.M)


class PayloadField:
    """An ``ir.model.fields`` record read with the definition of the
    project: label, tooltip, read-only flag, selection, comodel and
    currency field. Every other attribute is the record's."""

    def __init__(self, record, definition):
        self._record = record
        self._values = {
            "field_description": definition.get("field_description")
            or record.field_description,
            "help": definition.get("help") or False,
            "readonly": bool(definition.get("readonly")),
        }
        if definition.get("ttype") == "selection":
            self._selection = [
                tuple(item) for item in definition.get("selection") or []
            ]
            self._values["selection"] = repr(self._selection)
        if definition.get("relation"):
            self._values["relation"] = definition["relation"]
        if definition.get("currency_field"):
            self._values["currency_field"] = definition["currency_field"]

    def __getattr__(self, name):
        if name in self._values:
            return self._values[name]
        return getattr(self._record, name)

    def get_selection(self):
        if "selection" in self._values:
            return list(self._selection)
        return self._record.get_selection()


class CodeGeneratorWriter(models.Model):
    _inherit = "code.generator.writer"

    def _studio_project(self):
        project_id = self.env.context.get("erplibre_studio_project_id")
        if not project_id:
            return self.env["erplibre.studio.project"]
        return self.env["erplibre.studio.project"].sudo().browse(project_id).exists()

    def _get_model_constrains(self, cw, model, module):
        if self._studio_project():
            return None
        return super()._get_model_constrains(cw, model, module)

    def _get_model_access(self, module, model):
        if self._studio_project():
            return []
        return super()._get_model_access(module, model)

    def _get_model_rules(self, module, model):
        if self._studio_project():
            return []
        return super()._get_model_rules(module, model)

    def _set_model_xmlview_file(self, module, model, model_model):
        if self._studio_project():
            return None
        return super()._set_model_xmlview_file(module, model, model_model)

    def _set_model_xmlreport_file(self, module, model, model_model):
        if self._studio_project():
            return None
        return super()._set_model_xmlreport_file(module, model, model_model)

    def _set_model_xmldata_file(self, module, model, model_model):
        if self._studio_project():
            return None
        return super()._set_model_xmldata_file(module, model, model_model)

    def _get_model_fields_f2export(self, model, module):
        """Under a studio project, the fields of the project on ``model``,
        whatever their whitelist flag: the writer, on a model the module
        extends, exports only the flagged fields as soon as one field of
        the model is flagged, which would drop the other fields of the
        project. Same order and language context as the writer."""
        project = self._studio_project()
        if not project:
            return super()._get_model_fields_f2export(model, module)
        names = set(project._project_field_changes(model.model).mapped("field_name"))
        return (
            model.field_id.filtered(lambda f: f.name in names)
            .sorted(key=lambda r: r.code_generator_sequence)
            .with_context(lang=None)
        )

    def _generate_field_from_model(
        self, f2export, model_name, lst_field_inherit, dct_field_attr_diff
    ):
        project = self._studio_project()
        if project:
            change = project._field_add_change(f2export.model, f2export.name)
            if change:
                f2export = PayloadField(f2export, change._payload().get("field") or {})
        return super()._generate_field_from_model(
            f2export, model_name, lst_field_inherit, dct_field_attr_diff
        )

    def _set_model_py_file(self, module, model, model_model):
        path = super()._set_model_py_file(module, model, model_model)
        if self._studio_project() and path:
            cg_data = code_generator_data.get_code_generator_data(self.env)
            full = os.path.join(cg_data.module_path, path)
            with open(full, encoding="utf-8") as fh:
                content = fh.read()
            content = _COPIED_ATTRIBUTE.sub("", content)
            if "api." not in content and "_(" not in content:
                content = _WRITER_IMPORT.sub(
                    "from odoo import fields, models", content, count=1
                )
            with open(full, "w", encoding="utf-8") as fh:
                fh.write(content)
        return path

    def set_xml_views_file(self, module):
        super().set_xml_views_file(module)
        project = self._studio_project()
        if project:
            content = project_views_file(project)
            if content:
                cg_data = code_generator_data.get_code_generator_data(self.env)
                cg_data.write_file_str(VIEWS_FILE, content, data_file=True)


def project_views_file(project):
    """The XML data file of the inherited views of ``project``: one record
    per edited view, under the external id the database already uses."""
    root = etree.Element("odoo")
    for view in project.change_ids.mapped("view_id").sorted("id"):
        changes = [c._as_dict() for c in project._view_changes(view)]
        record = etree.SubElement(
            root,
            "record",
            id=project._studio_xmlname(view),
            model="ir.ui.view",
        )
        name = etree.SubElement(record, "field", name="name")
        name.text = f"{project.module_name}.{project._studio_xmlname(view)}"
        model = etree.SubElement(record, "field", name="model")
        model.text = view.model
        etree.SubElement(record, "field", name="inherit_id", ref=view.xml_id)
        priority = etree.SubElement(record, "field", name="priority")
        priority.text = str(STUDIO_PRIORITY)
        arch = etree.SubElement(record, "field", name="arch", type="xml")
        parser = etree.XMLParser(remove_blank_text=True)
        arch.append(etree.fromstring(studio_arch.view_arch(changes, view.type), parser))
    if not len(root):
        return ""
    body = etree.tostring(root, encoding="unicode", pretty_print=True)
    return '<?xml version="1.0" encoding="utf-8" ?>\n' + body
