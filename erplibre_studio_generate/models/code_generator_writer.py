# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""The code generator writer, narrowed to a studio project.

The writer exports everything it finds on the models of its module: the
SQL constraints, the access rights and record rules, the reports, the
actions and every view of the model. Under the context key
``erplibre_studio_project_id`` it exports what the project made only:

- a model the project creates gets its Python class (``x_name``, the
  fields of the project, the mail mixins of its chatter) and its
  constraints, reports and data like any model of a module;
- a model the project extends, which belongs to another module, gets the
  fields of the project only;
- the access rights and record rules are the project's, on its new models
  and on the existing models, whether the project adds fields to them or
  not;
- studio writes the views file itself: the default views of the new
  models, the inherited views, the window actions, the menu of each app
  and the menus of the models;
- studio writes the groups file itself: the category of each app that
  has groups, then the groups, each after the groups it implies; and the
  icon of each app, a copy of the icon chosen for it.

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
    MODEL_VIEW_PRIORITY,
    STUDIO_PRIORITY,
)
from odoo.tools import file_open

VIEWS_FILE = "views/erplibre_studio_views.xml"
GROUPS_FILE = "security/erplibre_studio_groups.xml"
HOOKS_FILE = "hooks.py"
# The pre_init_hook of a generated module that defines new models.
TAKE_OVER_HOOK = "erplibre_studio_take_over"

# The permissions of a record rule, as the writer names its fields.
RULE_PERMS = ("perm_read", "perm_create", "perm_write", "perm_unlink")

# Class attributes the writer copies from the extended model.
_COPIED_ATTRIBUTE = re.compile(r"^\s+_(order|rec_name) = .*$\n?", re.M)
# The import line of the writer; a studio model only declares fields.
_WRITER_IMPORT = re.compile(r"^from odoo import .*$", re.M)


class PayloadField:
    """An ``ir.model.fields`` record read with the definition of the
    project: label, tooltip, read-only flag, selection, comodel, currency
    field, and the relation of a relational field (the inverse of a
    one2many, the table and columns of a many2many, what a many2one does
    when its record is deleted). Every other attribute is the record's."""

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
        ttype = definition.get("ttype")
        if ttype == "many2one":
            self._values["on_delete"] = definition.get("on_delete") or "set null"
        elif ttype == "one2many" and definition.get("relation_field"):
            self._values["relation_field"] = definition["relation_field"]
        elif ttype == "many2many" and definition.get("relation_table"):
            for key in ("relation_table", "column1", "column2"):
                self._values[key] = definition[key]

    def __getattr__(self, name):
        if name in self._values:
            return self._values[name]
        return getattr(self._record, name)

    def get_selection(self):
        if "selection" in self._values:
            return list(self._selection)
        return self._record.get_selection()


class StudioModelProxy:
    """An ``ir.model`` record whose ``access_ids`` and ``rule_ids`` are
    those of a project: the emitters of the writer read every row of the
    model, whatever its module. Every other attribute is the record's."""

    def __init__(self, record, access_ids, rule_ids):
        self._record = record
        self._values = {"access_ids": access_ids, "rule_ids": rule_ids}

    def __getattr__(self, name):
        if name in self._values:
            return self._values[name]
        return getattr(self._record, name)


class CodeGeneratorWriter(models.Model):
    _inherit = "code.generator.writer"

    def _studio_project(self):
        project_id = self.env.context.get("erplibre_studio_project_id")
        if not project_id:
            return self.env["erplibre.studio.project"]
        return self.env["erplibre.studio.project"].sudo().browse(project_id).exists()

    def _studio_extends(self, model):
        """Whether ``model`` is a model the studio project extends, as
        opposed to one it creates."""
        project = self._studio_project()
        return bool(project) and model.model not in project._studio_new_models()

    def _studio_proxy(self, project, model):
        """``model`` with the access rights and record rules of
        ``project`` on it."""
        return StudioModelProxy(
            model,
            project.created_access_ids.filtered(lambda a: a.model_id == model),
            project.created_rule_ids.filtered(lambda r: r.model_id == model),
        )

    def _get_model_constrains(self, cw, model, module):
        if self._studio_extends(model):
            return None
        return super()._get_model_constrains(cw, model, module)

    def _get_model_access(self, module, model):
        project = self._studio_project()
        if project and not isinstance(model, StudioModelProxy):
            model = self._studio_proxy(project, model)
        return super()._get_model_access(module, model)

    def _get_model_rules(self, module, model):
        project = self._studio_project()
        if project and not isinstance(model, StudioModelProxy):
            model = self._studio_proxy(project, model)
        lines = super()._get_model_rules(module, model)
        return full_rules(lines, model.rule_ids) if project else lines

    def _get_group_data_name(self, group):
        """Under a studio project, an existing group by its external id under
        an installed module (``_studio_group_xmlid``): never one under
        « __export__ » or a module the generated module cannot depend on."""
        if self._studio_project():
            xmlid = self.env["erplibre.studio.project"]._studio_group_xmlid(group)
            if xmlid:
                return xmlid
        return super()._get_group_data_name(group)

    def _set_module_security(self, module, l_model_rules, l_model_csv_access):
        """Add the access rights and record rules of the project on the
        existing models it adds no field to: the writer reads those of the
        models of the module only. Then the groups file of the project,
        first in the data of the manifest: the access rights and the rules
        name its groups."""
        project = self._studio_project()
        if project:
            others = (
                project.created_access_ids.model_id | project.created_rule_ids.model_id
            ) - module.o2m_models
            for model in others.sorted("model"):
                l_model_csv_access += self._get_model_access(module, model)
                l_model_rules += self._get_model_rules(module, model)
            l_model_csv_access[:] = sorted(set(l_model_csv_access))
        res = super()._set_module_security(module, l_model_rules, l_model_csv_access)
        content = project_groups_file(project) if project else ""
        if content:
            cg_data = code_generator_data.get_code_generator_data(self.env)
            cg_data.write_file_str(
                GROUPS_FILE, content, data_file=True, insert_first=True
            )
            # The names and comments of the groups keep their value.
            cg_data.keep_xml_text(GROUPS_FILE)
        return res

    def _set_model_xmlview_file(self, module, model, model_model):
        if self._studio_project():
            return None
        return super()._set_model_xmlview_file(module, model, model_model)

    def _set_model_xmlreport_file(self, module, model, model_model):
        if self._studio_extends(model):
            return None
        return super()._set_model_xmlreport_file(module, model, model_model)

    def _set_model_xmldata_file(self, module, model, model_model):
        if self._studio_extends(model):
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
        names = set(project._studio_field_definitions(model.model))
        if not self._studio_extends(model):
            names.add("x_name")
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
            definitions = project._studio_field_definitions(f2export.model)
            if f2export.name in definitions:
                f2export = PayloadField(f2export, definitions[f2export.name][0])
        return super()._generate_field_from_model(
            f2export, model_name, lst_field_inherit, dct_field_attr_diff
        )

    def _set_model_py_file(self, module, model, model_model):
        """Under a studio project, an extended model loses the attributes
        the writer copies from the model (``_order``, ``_rec_name``); the
        import line keeps what the class uses."""
        path = super()._set_model_py_file(module, model, model_model)
        if self._studio_project() and path:
            cg_data = code_generator_data.get_code_generator_data(self.env)
            full = os.path.join(cg_data.module_path, path)
            with open(full, encoding="utf-8") as fh:
                content = fh.read()
            if self._studio_extends(model):
                content = _COPIED_ATTRIBUTE.sub("", content)
            if "api." not in content and "_(" not in content:
                content = _WRITER_IMPORT.sub(
                    "from odoo import fields, models", content, count=1
                )
            with open(full, "w", encoding="utf-8") as fh:
                fh.write(content)
        return path

    def set_xml_views_file(self, module):
        """The views file of the project, and the icon of each of its apps,
        which the menu of the app names."""
        super().set_xml_views_file(module)
        project = self._studio_project()
        if project:
            cg_data = code_generator_data.get_code_generator_data(self.env)
            content = project_views_file(project)
            if content:
                cg_data.write_file_str(VIEWS_FILE, content, data_file=True)
                # The names of the actions and views keep their value.
                cg_data.keep_xml_text(VIEWS_FILE)
            for app in project.app_ids:
                cg_data.write_file_binary(
                    app._studio_xml_names()["icon_path"], app_icon_bytes(app)
                )

    def set_manifest_file_extra(self, cw, module):
        super().set_manifest_file_extra(cw, module)
        project = self._studio_project()
        if project and project.new_model_ids:
            cw.emit(f"'pre_init_hook': '{TAKE_OVER_HOOK}',")

    def set_module_init_file_extra(self, module):
        """The hooks file of a module that defines new models, imported by
        the ``__init__.py`` of the module."""
        super().set_module_init_file_extra(module)
        project = self._studio_project()
        if project and project.new_model_ids:
            cg_data = code_generator_data.get_code_generator_data(self.env)
            cg_data.write_file_str(HOOKS_FILE, project_hooks_file(project, module))
            cg_data.add_module_init_path("", f"from .hooks import {TAKE_OVER_HOOK}")


def _license_line(license_name):
    return {
        "AGPL-3": "# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)",
        "LGPL-3": "# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl)",
    }.get(license_name, "")


def project_hooks_file(project, module):
    """The ``hooks.py`` of the module of ``project``: the pre_init_hook
    that takes over the custom models the project created in its
    database, before the first install, and the function the migration
    of each later version runs (``project_migration_file``). In another
    database it finds no such model and changes nothing."""
    models_literal = repr(tuple(sorted(project._studio_new_models())))
    license_line = _license_line(module.license)
    lines = [license_line, ""] if license_line else []
    lines += [
        "from odoo.exceptions import UserError",
        "",
        f"MODULE = {project.module_name!r}",
        "# The models of this module that ERPLibre studio creates first as",
        "# custom models in the database of its project.",
        f"MODELS = {models_literal}",
        "",
        "",
        "def take_over(cr):",
        '    """Make the custom models of the same names this module\'s own,',
        "    before it loads: Odoo builds a custom model again from its row,",
        "    in place of the class of this module. Their tables and records",
        "    stay; where no such model exists, nothing changes. A custom model",
        "    of this module that it does not define means a module older than",
        "    the database: loading it would delete that model with its",
        '    records, so the load stops."""',
        "    cr.execute(",
        '        "SELECT m.model FROM ir_model m JOIN ir_model_data d "',
        "        \"ON d.model = 'ir.model' AND d.res_id = m.id \"",
        "        \"WHERE d.module = %s AND m.state = 'manual' \"",
        '        "AND m.model NOT IN %s",',
        "        [MODULE, MODELS],",
        "    )",
        "    ahead = sorted(row[0] for row in cr.fetchall())",
        "    if ahead:",
        "        raise UserError(",
        '            "The database holds models of %s this version does not "',
        '            "define: %s. Generate the module again from its studio "',
        '            "project." % (MODULE, ", ".join(ahead))',
        "        )",
        "    cr.execute(",
        "        \"UPDATE ir_model SET state = 'base' \"",
        "        \"WHERE state = 'manual' AND model IN %s\",",
        "        [MODELS],",
        "    )",
        "",
        "",
        f"def {TAKE_OVER_HOOK}(env):",
        "    take_over(env.cr)",
        "",
    ]
    return "\n".join(lines)


def project_migration_file(project, license_name):
    """The ``migrations/<version>/pre-migration.py`` of the module of
    ``project``: Odoo runs it before it loads an upgraded module, so that
    the models Apply created since the install are taken over too."""
    license_line = _license_line(license_name)
    lines = [license_line, ""] if license_line else []
    lines += [
        f"from odoo.addons.{project.module_name}.hooks import take_over",
        "",
        "",
        "def migrate(cr, version):",
        "    take_over(cr)",
        "",
    ]
    return "\n".join(lines)


def _menu_ref(project, menu):
    """The full external id of ``menu``: its first one."""
    data = (
        project.env["ir.model.data"]
        .sudo()
        .search(
            [("model", "=", "ir.ui.menu"), ("res_id", "=", menu.id)],
            order="id",
            limit=1,
        )
    )
    return f"{data.module}.{data.name}"


def _field(parent, name, text=None, **attrs):
    node = etree.SubElement(parent, "field", name=name, **attrs)
    if text is not None:
        node.text = text
    return node


def project_views_file(project):
    """The XML data file of the views, actions and menus of ``project``,
    under the external ids the database already uses, in the order their
    references need: the default views of the new models, one inherited
    view per edited view, the window actions, then the top-level menu of
    each app a model goes in, with the icon the generation copies into
    the module, and the menus of the models."""
    root = etree.Element("odoo")
    parser = etree.XMLParser(remove_blank_text=True)
    lines = project.new_model_ids
    for line in lines:
        names = line._studio_xml_names()
        for view_type in studio_arch.MODEL_VIEW_TYPES:
            record = etree.SubElement(
                root, "record", id=names[view_type], model="ir.ui.view"
            )
            _field(record, "name", f"{line.model}.{view_type}")
            _field(record, "model", line.model)
            _field(record, "priority", str(MODEL_VIEW_PRIORITY))
            arch = _field(record, "arch", type="xml")
            arch.append(
                etree.fromstring(project._studio_default_arch(line, view_type), parser)
            )
    for view in project.change_ids.mapped("view_id").sorted("id"):
        changes = [c._as_dict() for c in project._view_changes(view)]
        record = etree.SubElement(
            root,
            "record",
            id=project._studio_xmlname(view),
            model="ir.ui.view",
        )
        _field(record, "name", f"{project.module_name}.{project._studio_xmlname(view)}")
        _field(record, "model", view.model)
        _field(record, "inherit_id", ref=view.xml_id)
        _field(record, "priority", str(STUDIO_PRIORITY))
        arch = _field(record, "arch", type="xml")
        arch.append(etree.fromstring(studio_arch.view_arch(changes, view.type), parser))
    for line in lines:
        names = line._studio_xml_names()
        record = etree.SubElement(
            root, "record", id=names["action"], model="ir.actions.act_window"
        )
        _field(record, "name", line.name.strip())
        _field(record, "res_model", line.model)
        _field(record, "view_mode", "list,form")
        _field(record, "search_view_id", ref=names["search"])
    for app in project.app_ids.filtered(lambda a: a._studio_menu_models()):
        names = app._studio_xml_names()
        etree.SubElement(
            root,
            "menuitem",
            id=names["menu"],
            name=app.name.strip(),
            web_icon=f"{project.module_name},{names['icon_path']}",
            sequence=str(app.menu_sequence),
        )
    for line in lines:
        names = line._studio_xml_names()
        if line.menu_mode == "app":
            parent = line.app_id.xml_name
        else:
            parent = _menu_ref(project, line.menu_parent_id)
        etree.SubElement(
            root,
            "menuitem",
            id=names["menu"],
            name=(line.menu_name or "").strip() or line.name.strip(),
            parent=parent,
            action=names["action"],
            sequence=str(line.menu_sequence),
        )
    if not len(root):
        return ""
    body = etree.tostring(root, encoding="unicode", pretty_print=True)
    return '<?xml version="1.0" encoding="utf-8" ?>\n' + body


def app_icon_bytes(app):
    """The bytes of the icon chosen for ``app``, else of the studio's."""
    module = "erplibre_studio"
    if app.icon:
        module = app.project_id._studio_icon_module(app.icon)
    with file_open(f"{module}/static/description/icon.png", "rb") as fh:
        return fh.read()


def full_rules(lines, rules):
    """``lines``, the XML lines of the records of ``rules`` the writer gives
    (``_get_model_rules``), each record with every field the studio sets:
    the writer leaves out ``groups`` for a rule without groups and each
    permission that is True, and an upgrade writes only the fields a record
    names, so that a rule made global, or a permission given back, would
    keep its former value in a database that upgrades the module."""
    result = []
    record = []
    rules = iter(rules)
    for line in lines:
        record.append(line)
        if line != "</record>\n":
            continue
        rule = next(rules)
        text = "".join(record)
        missing = []
        if '<field name="groups"' not in text:
            missing.append('<field name="groups" eval="[(6, 0, [])]" />')
        for perm in RULE_PERMS:
            if f'<field name="{perm}"' not in text:
                missing.append(f'<field name="{perm}" eval="{bool(rule[perm])}" />')
        result += record[:-1] + missing + record[-1:]
        record = []
    return result + record


def _group_ref(group):
    """The full external id of the existing group ``group``: its first under
    an installed module."""
    return group.env["erplibre.studio.project"]._studio_group_xmlid(group)


def _implication_order(groups):
    """``groups`` (group lines of a project) so that each one comes after
    the groups of the project it implies: a data file creates them in that
    order. The groups imply each other in no cycle (``_check_studio_group``)."""
    ordered = groups.browse()
    todo = groups
    while todo:
        ready = todo.filtered(lambda g: not (g.implied_line_ids & todo))
        if not ready:
            # A cycle, which the constraint refuses: keep the given order.
            ready = todo
        ordered |= ready
        todo -= ready
    return ordered


def project_groups_file(project):
    """The XML data file of the groups of ``project``: the category of each
    app that has groups, then each group in its category, after the groups
    it implies. ``implied_ids`` lists exactly the groups the project gives
    it (``(6, 0, ...)``): an upgrade drops an implication the project
    dropped; the users keep their groups. Empty without group."""
    groups = project.group_line_ids
    if not groups:
        return ""
    root = etree.Element("odoo")
    for app in project.app_ids.filtered("group_line_ids"):
        record = etree.SubElement(
            root,
            "record",
            id=app._studio_xml_names()["category"],
            model="ir.module.category",
        )
        _field(record, "name", app.name.strip())
        _field(record, "sequence", str(app.menu_sequence))
    for group in _implication_order(groups):
        record = etree.SubElement(root, "record", id=group.xml_name, model="res.groups")
        _field(record, "name", group.name.strip())
        _field(record, "category_id", ref=group.app_id._studio_xml_names()["category"])
        refs = [_group_ref(g) for g in group.implied_group_ids.sorted("id")]
        refs += group.implied_line_ids.sorted(lambda g: g.xml_name).mapped("xml_name")
        implied = ", ".join(f"ref({ref!r})" for ref in refs)
        _field(record, "implied_ids", eval=f"[(6, 0, [{implied}])]")
        # Written empty as well: an upgrade writes only the fields a record
        # names, and would keep a comment the project cleared.
        if (group.comment or "").strip():
            _field(record, "comment", group.comment.strip())
        else:
            _field(record, "comment", eval="False")
    body = etree.tostring(root, encoding="unicode", pretty_print=True)
    return '<?xml version="1.0" encoding="utf-8" ?>\n' + body
