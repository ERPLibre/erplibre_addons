# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models
from odoo.exceptions import UserError

from .. import arch as studio_arch
from .erplibre_studio_project import (
    PENDING_VIEW_OPERATIONS,
    PERMS,
    PREVIEW_KEY,
    protected_model,
)
from .studio_pending import added_view, is_added_view, is_pending_view, pending_view

FIELD_ATTRIBUTES = [
    "string",
    "type",
    "required",
    "readonly",
    "relation",
    "selection",
    "help",
    "store",
    "groupable",
    "searchable",
    "sortable",
    "aggregator",
]

PROJECT_ACTIONS = (
    "action_apply",
    "action_discard",
    "action_revert",
    "action_undo",
    "action_approve",
    "action_unapprove",
)
# The actions that remove from the database what the user confirmed.
DIGEST_ACTIONS = ("action_apply", "action_revert")
# The modes of the preview of a model not created yet.
PREVIEW_MODES = ("simulation", "real")
# The view types the editor lists after VIEW_TYPES, with why it does not
# edit them.
UNSUPPORTED_VIEW_TYPES = ("gantt",)
# The ``reason_code`` of a view type the editor does not open (``_view_list``):
# a type of OPTIONAL_VIEW_MODULES without its module, a type the studio does
# not edit, a type no installed module provides, a type a model not created
# yet cannot have before Apply, an activity view of a model without
# activities (mail.activity.mixin), a map of a model without the field
# web_view_leaflet_map always reads (LEAFLET_DATE_FIELD) on a database where
# a new field needs the x_ prefix, a GeoEngine view of a model without a
# geo field in the database, a type the model has no view of.
# {view type: name of its template the canvas edits as a card}: a
# hierarchy draws each node with its « hierarchy-box », an activity view the
# record cell of each row with its « activity-box », a GeoEngine view the
# popup of a record with its « info_box ». A kanban takes « card », or
# « kanban-box » as former versions name it.
CARD_TEMPLATES = {
    "hierarchy": "hierarchy-box",
    "activity": "activity-box",
    "geoengine": studio_arch.GEO_INFO_BOX,
}
VIEW_REASONS = (
    "needs_module",
    "not_editable",
    "not_installed",
    "apply_first",
    "needs_activity",
    "needs_field",
    "needs_geo_field",
    "no_view",
)
# How many members ``get_group_members`` and ``get_group_losses`` name at
# most; their ``count`` says how many there are.
MEMBERS_SHOWN = 20


class ErplibreStudioEditor(models.AbstractModel):
    """The server side of the studio editor. Every call needs the Settings
    group and the developer mode; each operation answers with the new
    editor payload, computed from the draft of the project."""

    _name = "erplibre.studio.editor"
    _description = "ERPLibre studio editor"

    @api.model
    def _check_studio_access(self):
        self.env["erplibre.developer"]._check_panel_access()

    @api.model
    def _resolve_view(self, model, view_id, view_type, project=None):
        """The primary view the editor inherits: ``view_id``, or the default
        view of ``model`` for ``view_type``; for a model of ``project`` not
        created yet, its pending default view (``StudioPendingView``); for a
        type ``model`` has no view of, the view ``project`` adds before
        Apply creates it (``StudioAddedView``)."""
        Project = self.env["erplibre.studio.project"]
        if view_type not in Project._view_types():
            raise UserError(
                self.env._("The studio does not edit %(type)s views.", type=view_type)
            )
        if model not in self.env:
            line = project._studio_pending_line(model) if project else None
            if not line:
                raise UserError(self.env._("Unknown model %(model)s.", model=model))
            if view_type not in studio_arch.MODEL_VIEW_TYPES:
                raise UserError(
                    self.env._(
                        "Apply the model first: %(type)s needs its records.",
                        type=view_type,
                    )
                )
            return pending_view(line, view_type)
        View = self.env["ir.ui.view"].sudo()
        view = View.browse(int(view_id)).exists() if view_id else View
        if not view:
            view = View.browse(View.default_view(model, view_type))
        if not view and project:
            added = project._studio_added_view(model, view_type)
            if added:
                return added
        if not view:
            raise UserError(
                self.env._(
                    "%(model)s has no %(type)s view to inherit.",
                    model=model,
                    type=view_type,
                )
            )
        if view.model != model or view.type != view_type or view.mode != "primary":
            raise UserError(
                self.env._(
                    "The studio inherits a primary %(type)s view.",
                    type=view_type,
                )
            )
        return view

    @api.model
    def _read_project(self, project_id):
        """The project ``project_id`` as a read sees it: not opened, its
        editor and its revision unchanged."""
        Project = self.env["erplibre.studio.project"]
        project = Project.browse(int(project_id or 0)).exists()
        if not project:
            raise UserError(self.env._("Choose or create a studio project first."))
        return project

    @api.model
    def _project(self, project_id, pick_project=True, model=None):
        """The project ``project_id``; without one, unless ``pick_project``
        is False, the project that creates ``model``, else the last project
        of the user. Opening a project makes the user its editor, the one
        who sees its draft."""
        Project = self.env["erplibre.studio.project"]
        project = Project.browse(int(project_id)).exists() if project_id else Project
        if not project and pick_project and model:
            project = (
                self.env["erplibre.studio.model"]
                .search([("model", "=", model)], limit=1)
                .project_id
            )
        if not project and pick_project:
            project = Project.search([("user_id", "=", self.env.uid)], limit=1)
        if project and project.user_id != self.env.user:
            project.user_id = self.env.user
        return project

    @api.model
    def action_customize(
        self,
        model,
        view_id=False,
        view_type="form",
        action_id=False,
        project_id=False,
    ):
        """The client action of the editor on a view; on the default view of
        a model of the project ``project_id`` not created yet."""
        self._check_studio_access()
        Project = self.env["erplibre.studio.project"]
        project = Project.browse(int(project_id or 0)).exists()
        view = self._resolve_view(model, view_id, view_type, project)
        return {
            "type": "ir.actions.client",
            "tag": "erplibre_studio.editor",
            "name": self.env._("Studio"),
            "target": "current",
            "params": {
                "res_model": model,
                "view_id": view.id,
                "view_type": view.type,
                "action_id": action_id or False,
                "project_id": project_id or False,
            },
        }

    @api.model
    def _fields_payload(self, model, project):
        """The fields of ``model`` (simulated for a model of the project not
        created yet) with the new fields of the project on it, flagged
        ``project``, ``pending`` until Apply creates them, their
        ``definition``, ``inverse_protected`` for a many2one whose comodel
        takes no inverse one2many, and ``name_auto``: whether the technical
        name still follows the label (False for an inverse field, which the
        field that creates it names)."""
        line = project._studio_pending_line(model) if project else None
        if line:
            info = project._studio_simulated_fields(line)
            names = set()
        else:
            Model = self.env[model]
            info = Model.fields_get(attributes=FIELD_ATTRIBUTES)
            for field_info in info.values():
                studio_arch.unqueryable_flags(field_info)
            names = set(Model._fields)
        definitions = project._studio_field_definitions(model) if project else {}
        for name, (definition, change) in definitions.items():
            entry = info.setdefault(
                name,
                {
                    "string": definition.get("field_description"),
                    "type": definition.get("ttype"),
                    "relation": definition.get("relation") or False,
                    "selection": definition.get("selection") or [],
                    "required": definition.get("required", False),
                    "readonly": definition.get("readonly", False),
                    "help": definition.get("help") or "",
                    "store": True,
                    # Searched, grouped or added up once Apply creates it.
                    "groupable": False,
                    "searchable": False,
                    "sortable": False,
                    "aggregator": False,
                },
            )
            entry["project"] = True
            entry["pending"] = name not in names
            entry["definition"] = definition
            entry["name_auto"] = bool(
                change.model == model
                and change.field_name == name
                and change._payload().get("name_auto", True)
            )
            if definition.get("ttype") == "many2one":
                # The studio adds no inverse one2many to such a comodel.
                entry["inverse_protected"] = protected_model(definition.get("relation"))
        return info

    @api.model
    def _palette(self, view_type, arch, fields_info):
        """The fields the editor offers to drop: those the view does not
        show yet, that its type can use. A pivot or a graph field says on
        which ``axes`` it goes: a graph groups by « row » only."""
        if view_type == "search":
            shown = {n.get("name") for n in arch.iter("field")}
        else:
            shown = studio_arch.shown_field_names(arch, view_type)
        palette = []
        Project = self.env["erplibre.studio.project"]
        for name, info in fields_info.items():
            if name in shown or name == "id" or name.startswith("__"):
                continue
            item = {
                "name": name,
                "string": info.get("string") or name,
                "type": info.get("type"),
            }
            if view_type == "form" and Project._studio_dms_field(name, info):
                # Dropped as the documents tree of dms_field (« special »).
                item["string"] = self.env._("Documents (DMS)")
                item["special"] = studio_arch.DMS_VIEW_TYPE
            if view_type == "search" and not info.get("searchable"):
                continue
            if view_type not in ("form", "list") and (
                info.get("type") in studio_arch.UNQUERYABLE_TYPES
            ):
                # Odoo neither searches nor groups by it, whatever
                # « searchable » or « groupable » reads.
                continue
            if view_type == "calendar" and info.get("type") in (
                "one2many",
                "binary",
            ):
                # The popover of an event shows neither.
                continue
            if view_type == "leaflet_map" and not self._leaflet_fits(info):
                # A map shows a field through a lane only.
                continue
            if (
                view_type == "geoengine"
                and info.get("type") in studio_arch.GEO_TYPES
                and name in studio_arch.arch_field_names(arch)
            ):
                # A geo field goes among the loaded fields only, once.
                continue
            if view_type in studio_arch.AXIS_VIEW_TYPES:
                axes = [
                    axis
                    for axis in studio_arch.AXIS_VIEW_TYPES[view_type]
                    if axis != "measure" and info.get("groupable")
                ]
                if self._measurable(info):
                    axes.append("measure")
                if not axes:
                    continue
                item["axes"] = axes
            palette.append(item)
        return sorted(palette, key=lambda f: (f["string"] or "").lower())

    @api.model
    def _dms_layout(self, model, fields_info):
        """The keys a form adds to its layout when ``model`` holds the DMS
        directories of its records (``_studio_dms_field``): whether a
        dms.field.template of dms_field configures them (``dms_template``;
        without one the documents tree stays empty) and the external id of
        the action that lists the templates (``dms_template_action``)."""
        name = studio_arch.DMS_FIELD
        Project = self.env["erplibre.studio.project"]
        Template = self.env.get("dms.field.template")
        if Template is None or not Project._studio_dms_field(
            name, fields_info.get(name) or {}
        ):
            return {}
        return {
            "dms_template": bool(Template.sudo().search_count([("model", "=", model)])),
            "dms_template_action": "dms_field.action_dms_field_template",
        }

    @api.model
    def _leaflet_fits(self, info):
        """Whether the field ``info`` fits a lane of a map: a stored float
        (a coordinate), a text of LEAFLET_TEXT_TYPES (the popup) or a
        binary (the marker image)."""
        ttype = info.get("type")
        return (
            (ttype == "float" and info.get("store"))
            or ttype in studio_arch.LEAFLET_TEXT_TYPES
            or ttype == "binary"
        )

    @api.model
    def _measurable(self, info):
        return bool(
            info.get("type") in studio_arch.NUMBER_TYPES and info.get("aggregator")
        )

    @api.model
    def _choices(self, fields_info, model=None):
        """The values the editor offers for each kind of attribute value
        (see ``SETTABLE_ATTRIBUTES``): [[value, label]] lists, those of
        ``CHOICES`` included. A field of the project not yet applied is in
        none of them. ``model`` is the model of the view, for the kinds
        whose values depend on it."""

        def fields_where(predicate):
            items = [
                [name, info.get("string") or name]
                for name, info in fields_info.items()
                if not info.get("pending") and predicate(info)
            ]
            return sorted(items, key=lambda item: (item[1] or "").lower())

        def queryable(flag):
            # The flag of fields_get, false for UNQUERYABLE_TYPES, which
            # Odoo neither searches, sorts nor groups by.
            return lambda f: (
                f.get(flag) and f.get("type") not in studio_arch.UNQUERYABLE_TYPES
            )

        def stored(types):
            return lambda f: f.get("type") in types and f.get("store")

        def to_model(ttype):
            # A relation of ``model`` to itself: the parent and the
            # children of a hierarchy.
            return lambda f: (
                model and f.get("type") == ttype and f.get("relation") == model
            )

        choices = {
            kind: [[value, value] for value in values]
            for kind, values in studio_arch.CHOICES.items()
        }
        return {
            **choices,
            "group_field": fields_where(queryable("groupable")),
            "relation_group_field": fields_where(
                lambda f: f.get("groupable")
                and f.get("type") in studio_arch.RELATION_TYPES
            ),
            "date_field": fields_where(stored(studio_arch.DATE_TYPES)),
            "color_field": fields_where(stored(studio_arch.CALENDAR_COLOR_TYPES)),
            "bool_field": fields_where(stored(("boolean",))),
            "number_field": fields_where(stored(("integer", "float"))),
            "measure": fields_where(self._measurable),
            "search_field": fields_where(queryable("searchable")),
            "sort_field": fields_where(queryable("sortable")),
            "bool": [["True", "True"], ["False", "False"]],
            "calendar_filter": [["True", "True"]],
            "parent_field": fields_where(
                lambda f: to_model("many2one")(f) and f.get("store")
            ),
            "child_field": fields_where(to_model("one2many")),
            "coordinate_field": fields_where(stored(("float",))),
            "text_field": fields_where(
                lambda f: f.get("type") in studio_arch.LEAFLET_TEXT_TYPES
            ),
            "image_field": fields_where(lambda f: f.get("type") == "binary"),
            "axis": [[axis, axis] for axis in studio_arch.PIVOT_AXES],
            "graph_axis": [[axis, axis] for axis in studio_arch.GRAPH_AXES],
            "interval": [[i, i] for i in studio_arch.INTERVALS],
            "widget": [[w, w] for w in studio_arch.WIDGETS],
        }

    @api.model
    def _layout(self, view_type, arch, fields_info=None):
        """The part of the payload proper to ``view_type``: where its zones
        are in the arch (paths of the blocks). ``fields_info``: the fields
        of the model ({name: {type}}), which place the fields of a graph."""
        path = lambda node: studio_arch.node_xpath(arch, node)  # noqa: E731
        root = f"/{arch.tag}"
        loaded = [c.get("name") for c in studio_arch.elements(arch) if c.tag == "field"]
        if view_type == "kanban" or view_type in CARD_TEMPLATES:
            # Each card template (CARD_TEMPLATES) compiles as a kanban card
            # does; no widget of WIDGETS goes in them.
            templates = studio_arch.templates_of(arch)
            if view_type in CARD_TEMPLATES:
                card = templates.get(CARD_TEMPLATES[view_type])
            else:
                card = templates.get("card")
                if card is None:
                    card = templates.get("kanban-box")
            return {
                "root": root,
                "card": path(card) if card is not None else False,
                "templates": {name: path(node) for name, node in templates.items()},
                "loaded_fields": loaded,
                "widgets": (
                    {k: list(v) for k, v in studio_arch.WIDGETS.items()}
                    if view_type == "kanban"
                    else {}
                ),
            }
        if view_type == "timeline":
            item = studio_arch.templates_of(arch).get("timeline-item")
            return {
                "root": root,
                "template": path(item) if item is not None else False,
                "loaded_fields": loaded,
                "colors": studio_arch.colors_rules(arch.get("colors")),
                "color_operators": list(studio_arch.COLOR_OPERATORS),
                "color_types": list(studio_arch.COLOR_FIELD_TYPES),
            }
        if view_type == "search":
            kinds = {"fields": [], "filters": [], "group_bys": []}
            for node in arch.iter("field", "filter"):
                if node.tag == "field":
                    kinds["fields"].append(path(node))
                elif studio_arch.group_by_of(node):
                    kinds["group_bys"].append(path(node))
                else:
                    kinds["filters"].append(path(node))
            return {
                "root": root,
                **kinds,
                "operators": {
                    ttype: list(ops)
                    for ttype, ops in studio_arch.SEARCH_OPERATORS.items()
                },
            }
        if view_type == "calendar":
            # The popover of an event shows the <field> children; the root
            # attributes load their own fields.
            return {
                "root": root,
                "popover": [
                    path(c) for c in studio_arch.elements(arch) if c.tag == "field"
                ],
                "loaded_by_attributes": [
                    arch.get(attribute)
                    for attribute in studio_arch.CALENDAR_FIELD_ATTRIBUTES
                    if arch.get(attribute)
                ],
            }
        if view_type == "leaflet_map":
            # The lanes of a map are its field attributes; a lane takes a
            # new field of the types of ``new_field_types``.
            settable = studio_arch.SETTABLE_ATTRIBUTES["leaflet_map"]["leaflet_map"]
            return {
                "root": root,
                "lanes": {
                    attribute: arch.get(attribute) or False
                    for attribute in studio_arch.LEAFLET_FIELD_ATTRIBUTES
                },
                "loaded_fields": loaded,
                "new_field_types": {
                    attribute: list(
                        studio_arch.LEAFLET_NEW_FIELD_TYPES.get(settable[attribute], ())
                    )
                    for attribute in studio_arch.LEAFLET_FIELD_ATTRIBUTES
                },
            }
        if view_type in studio_arch.AXIS_VIEW_TYPES:
            axes = {axis: [] for axis in studio_arch.AXIS_VIEW_TYPES[view_type]}
            others = []
            for node in studio_arch.elements(arch):
                if node.tag != "field":
                    continue
                if view_type == "graph":
                    axis = self._graph_axis(node, fields_info or {})
                else:
                    axis = node.get("type")
                (axes[axis] if axis in axes else others).append(path(node))
            return {"root": root, "axes": axes, "others": others}
        return {"root": root}

    @api.model
    def _graph_axis(self, node, fields_info):
        """The axis a graph reads the <field> ``node`` on, as its arch parser
        does: none for an invisible field; « measure » for a field of that
        type; « row », a group-by, for any other field of a type of
        GRAPH_GROUP_TYPES (``fields_info`` gives the types), whatever its
        « type »; else none."""
        if node.get("invisible") in ("1", "True"):
            return None
        if node.get("type") == "measure":
            return "measure"
        info = fields_info.get(node.get("name")) or {}
        if info.get("type") in studio_arch.GRAPH_GROUP_TYPES:
            return "row"
        return None

    @api.model
    def _view_type_labels(self):
        """{view type: label} in the language of the user: the types
        ir.ui.view knows, and those of VIEW_TYPES and UNSUPPORTED_VIEW_TYPES
        no installed module adds."""
        labels = {
            "timeline": self.env._("Timeline"),
            "hierarchy": self.env._("Hierarchy"),
            "calendar": self.env._("Calendar"),
            "graph": self.env._("Graph"),
            "gantt": self.env._("Gantt"),
            "activity": self.env._("Activity"),
            "leaflet_map": self.env._("Map (Leaflet)"),
            "geoengine": self.env._("GeoEngine"),
        }
        field = self.env["ir.ui.view"]._fields["type"]
        labels.update(dict(field._description_selection(self.env)))
        return labels

    @api.model
    def _view_list(self, model, view, project):
        """[{type, label, view_id, xml_id, exists, pending, added, editable,
        reason, reason_code, description, changes}]: for each view type of
        VIEW_TYPES, then of UNSUPPORTED_VIEW_TYPES, the default view of ``model``
        (``view``, the view on screen, for its type) and whether the studio
        edits it, else why not (``reason``, in the language of the user, and
        ``reason_code``, see VIEW_REASONS). ``changes``: how many changes of
        ``project`` it holds. A model of the project not created yet has
        its pending default views (``view_id`` False, ``pending``). A view
        ``project`` adds is ``added``, and ``pending`` until Apply creates
        it; an entry « no_view » is a type the project can add, and its
        ``description`` says what adding it also creates, else False."""
        Project = self.env["erplibre.studio.project"]
        editable_types = Project._view_types()
        known = set(self.env["ir.ui.view"]._fields["type"].get_values(self.env))
        labels = self._view_type_labels()
        pending = is_pending_view(view)
        View = self.env["ir.ui.view"].sudo()
        project_changes = (
            project.change_ids if project else self.env["erplibre.studio.change"]
        )
        result = []
        for view_type in studio_arch.VIEW_TYPES + UNSUPPORTED_VIEW_TYPES:
            label = labels.get(view_type, view_type)
            entry = {
                "type": view_type,
                "label": label,
                "view_id": False,
                "xml_id": False,
                "exists": False,
                "pending": False,
                "added": False,
                "editable": False,
                "reason": False,
                "reason_code": False,
                "description": False,
                "changes": 0,
            }
            if pending:
                record = view.line
                if view_type in studio_arch.MODEL_VIEW_TYPES:
                    entry.update(exists=True, pending=True)
                    entry["changes"] = len(
                        project_changes.filtered(
                            lambda c, t=view_type: c.model_line_id == record
                            and c.view_type == t
                        )
                    )
            elif view_type in known:
                line = (
                    project._studio_view_line(model, view_type)
                    if project
                    else self.env["erplibre.studio.view"]
                )
                if view_type == view.type:
                    record = view
                else:
                    record = View.browse(View.default_view(model, view_type))
                    if not record and line and not line.applied:
                        record = added_view(line)
                if record:
                    added = is_added_view(record)
                    entry.update(
                        view_id=record.id or False,
                        xml_id=record.xml_id or False,
                        exists=True,
                        pending=added,
                        added=added or bool(line and record == line.view_id),
                    )
                    entry["changes"] = (
                        len(project._view_changes(record)) if project else 0
                    )
            if view_type not in editable_types:
                if view_type in studio_arch.OPTIONAL_VIEW_MODULES:
                    code = "needs_module"
                elif view_type in known:
                    code = "not_editable"
                else:
                    code = "not_installed"
            elif pending and view_type not in studio_arch.MODEL_VIEW_TYPES:
                code = "apply_first"
            elif not entry["exists"] and (need := self._view_need(view_type, model)):
                code = need
            elif (
                view_type == "leaflet_map"
                and not entry["exists"]
                and model in self.env
                and studio_arch.LEAFLET_DATE_FIELD not in self.env[model]._fields
            ):
                if Project._studio_field_name_rule()["prefix_required"]:
                    code = "needs_field"
                else:
                    # Add a view creates the field with the map
                    # (``_studio_add_leaflet_date``).
                    code = "no_view"
                    entry["description"] = self.env._(
                        "The map also creates the %(field)s field it reads.",
                        field=studio_arch.LEAFLET_DATE_FIELD,
                    )
            elif not entry["exists"]:
                code = "no_view"
            else:
                code = False
            entry["editable"] = not code
            entry["reason_code"] = code
            entry["reason"] = self._view_reason(code, label, model, view_type)
            result.append(entry)
        return result

    @api.model
    def _view_need(self, view_type, model):
        """The ``reason_code`` of a ``view_type`` view ``model`` lacks what
        it reads for: « needs_activity » for an activity view of a model
        without activities, « needs_geo_field » for a GeoEngine view of a
        model without a geo field in the registry; False otherwise."""
        Project = self.env["erplibre.studio.project"]
        if view_type == "activity" and not Project._studio_has_activities(model):
            return "needs_activity"
        if view_type == "geoengine" and not Project._studio_geo_fields(model):
            return "needs_geo_field"
        return False

    @api.model
    def _view_reason(self, code, label, model, view_type=None):
        """The text of the ``reason_code`` ``code`` of ``_view_list`` for
        the view type ``view_type`` labelled ``label``, or False for none.
        « needs_module » names the module of OPTIONAL_VIEW_MODULES."""
        if code == "needs_module":
            return self.env._(
                "Install the %(module)s module to edit a %(type)s view.",
                module=studio_arch.OPTIONAL_VIEW_MODULES[view_type],
                type=label.lower(),
            )
        if code == "not_editable":
            return self.env._(
                "The studio does not edit %(type)s views yet.", type=label
            )
        if code == "not_installed":
            return self.env._(
                "No installed module provides %(type)s views.", type=label
            )
        if code == "apply_first":
            return self.env._(
                "Apply the model first: %(type)s needs its records.", type=label
            )
        if code == "needs_activity":
            return self.env._(
                "%(model)s has no activities: an activity view needs the model "
                "to inherit mail.activity.mixin (a chatter).",
                model=model,
            )
        if code == "needs_field":
            return self.env._(
                "The map of web_view_leaflet_map reads a date_localization "
                "field, which %(model)s does not have: it would show no marker.",
                model=model,
            )
        if code == "needs_geo_field":
            return self.env._(
                "A GeoEngine view needs a geo field on %(model)s: add one to its "
                "form and Apply first.",
                model=model,
            )
        if code == "no_view":
            return self.env._(
                "%(model)s has no %(type)s view to inherit.", model=model, type=label
            )
        return False

    @api.model
    def get_editor_data(
        self, model, view_id, view_type, project_id=False, pick_project=True
    ):
        """The editor payload of a view: the blocks of its draft arch, the
        fields of the model, the changes of the project and its projects,
        and what its view type allows (operations, attributes, layout).
        ``pick_project``: see ``_project``."""
        self._check_studio_access()
        Project = self.env["erplibre.studio.project"]
        project = self._project(project_id, pick_project, model)
        view = self._resolve_view(model, view_id, view_type, project)
        if project:
            arch, errors = project._draft_arch(view, track=True)
        else:
            arch, errors = view._get_combined_arch(), {}
        fields_info = self._fields_payload(model, project)
        blocks = studio_arch.arch_blocks(arch, view.type, fields_info)
        paths = studio_arch.change_paths(arch)
        studio_arch.strip_change_marks(arch)
        changes = []
        if project:
            for change in project._view_changes(view):
                spec = change._as_dict()
                changes.append(
                    {
                        "id": change.id,
                        "type": change.change_type,
                        "kind": studio_arch.change_kind(spec),
                        # The attribute a « set_attribute » writes, else False.
                        "attribute": (
                            change.change_type == "set_attribute"
                            and spec["payload"].get("attribute")
                        )
                        or False,
                        "summary": change.summary,
                        "xpath": change.xpath,
                        "path": paths.get(str(change.id)) or False,
                        "error": errors.get(change.id) or False,
                    }
                )
        pending = is_pending_view(view)
        if pending:
            sample = False
            model_name = view.line.name
            view_types = list(studio_arch.MODEL_VIEW_TYPES)
        else:
            Model = self.env[model]
            sample = Model.search([], limit=1).id if view.type == "form" else False
            model_name = self.env["ir.model"]._get(model).name
            view_types = list(Project._view_types())
        return {
            "model": model,
            "model_name": model_name,
            "view_type": view.type,
            "view_types": view_types,
            "view_list": self._view_list(model, view, project),
            "view": {
                "id": view.id,
                "name": view.name,
                "xml_id": view.xml_id or False,
                "pending": pending,
                "model_line_id": view.line.id if pending else False,
                "added": self._added_payload(project, view),
            },
            "blocks": blocks,
            "layout": {
                **self._layout(view.type, arch, fields_info),
                **(self._dms_layout(model, fields_info) if view.type == "form" else {}),
            },
            "operations": [
                op
                for op in studio_arch.VIEW_OPERATIONS[view.type]
                if not pending or op in PENDING_VIEW_OPERATIONS.get(view.type, ())
            ],
            "hide_mode": studio_arch.hide_mode(view.type),
            "settable": studio_arch.SETTABLE_ATTRIBUTES.get(view.type, {}),
            "required_attributes": {
                tag: list(names)
                for (vtype, tag), names in studio_arch.REQUIRED_ATTRIBUTES.items()
                if vtype == view.type
            },
            "choices": self._choices(fields_info, model),
            "fields": fields_info,
            "palette": self._palette(view.type, arch, fields_info),
            "field_types": list(Project._studio_field_types()),
            # The form of a geometry field shows a map that needs a geoengine
            # view of the model: the inspector says so while there is none.
            "geo_view_missing": bool(
                Project._studio_geo_available()
                and (project or Project)._studio_geo_view_missing(model)
            ),
            "changes": changes,
            "errors": [e for e in errors.values()],
            "project": self._project_payload(project) if project else False,
            "projects": [
                {
                    "id": p.id,
                    "name": p.name,
                    "module_name": p.module_name,
                    "state": p.state,
                }
                for p in Project.search([])
            ],
            "preview_key": PREVIEW_KEY,
            "sample_res_id": sample or False,
            "mail_available": Project._studio_mail_available(),
            "field_name_rule": (project or Project)._studio_field_name_rule(),
            "model_name_rule": (project or Project)._studio_model_name_rule(),
        }

    @api.model
    def _added_payload(self, project, view):
        """{line_id, applied, name, xml_id, layers} of the view line of
        ``project`` behind ``view`` (see ``_studio_view_line_of``), or False
        when ``view`` is not a view the project adds. ``layers``: the layers
        of a GeoEngine view (``erplibre.studio.geo.layer._payload``); such a
        view also answers what a layer may read, ``geo_fields`` [[name,
        label]] and ``attribute_fields`` [[name, label, numeric]]."""
        line = project._studio_view_line_of(view) if project else False
        if not line:
            return False
        payload = {
            "line_id": line.id,
            "applied": line.applied,
            "name": line._studio_view_name(),
            "xml_id": f"{project.module_name}.{line._studio_xml_name()}",
            "layers": line.layer_ids._payload(),
        }
        if line.view_type == "geoengine":
            Model = self.env[line.model]
            label = lambda name: Model._fields[name].string or name  # noqa: E731
            payload["geo_fields"] = [
                [name, label(name)] for name in project._studio_geo_fields(line.model)
            ]
            attributes = project._studio_geo_attribute_fields(line.model)
            payload["attribute_fields"] = sorted(
                (
                    [name, label(name), ttype in studio_arch.GEO_NUMBER_TYPES]
                    for name, ttype in attributes.items()
                ),
                key=lambda item: item[1].lower(),
            )
        return payload

    @api.model
    def _project_payload(self, project):
        """The project as the editor shows it; ``state_label`` is the label
        of its state in the language of the user. ``app`` is its first app,
        for an editor of a single app. ``module_state`` is the state of the
        module named ``module_name`` in the database, False when none has
        that name: the inspector names the module that holds a new field."""
        states = dict(project._fields["state"]._description_selection(self.env))
        first = project.app_ids[:1]
        pending_models = project.new_model_ids.filtered(lambda m: not m.applied)
        approver = project.approved_uid
        return {
            "id": project.id,
            "name": project.name,
            "module_name": project.module_name,
            "module_state": project.module_state or False,
            "state": project.state,
            "state_label": states.get(project.state, project.state),
            "revision": project.draft_revision,
            "preview_value": f"{project.id}:{project.draft_revision}",
            "change_count": project.change_count,
            "item_count": project.item_count,
            "applied": bool(project.applied_snapshot),
            "app": (
                {"name": first.name, "icon": first.icon or False} if first else False
            ),
            "apps": [self._app_payload(app) for app in project.app_ids],
            "groups": [self._group_payload(group) for group in project.group_line_ids],
            "models": [self._model_payload(line) for line in project.new_model_ids],
            # The menus Apply made, as the web client shows them: when they
            # change, the editor reloads the menus of the web client.
            "menus": [
                [menu.id, menu.name, menu.web_icon or False, menu.parent_id.id]
                for menu in project.created_menu_ids.sudo().sorted("id")
            ],
            "access": [self._access_payload(line) for line in project.access_line_ids],
            "rules": [self._rule_payload(rule) for rule in project.rule_line_ids],
            "added_views": [
                self._view_line_payload(line) for line in project.view_line_ids
            ],
            "approved": project.approved,
            "approved_by": [approver.id, approver.name] if approver else False,
            "approved_date": (
                fields.Datetime.to_string(project.approved_date)
                if project.approved_date
                else False
            ),
            "real_preview_available": bool(project.approved and pending_models),
            "applied_date": (
                fields.Datetime.to_string(project.applied_date)
                if project.applied_date
                else False
            ),
            "counts": self._project_counts(project),
            "touched_models": self._touched_models(project),
        }

    @api.model
    def _view_line_payload(self, line):
        """A view line as the editor shows it: its model and type, whether
        Apply created it, and how many changes it holds."""
        project = line.project_id
        label = self._view_type_labels().get(line.view_type, line.view_type)
        changes = project.change_ids.filtered(
            lambda c: c.view_line_id == line
            or (line.view_id and c.view_id == line.view_id)
        )
        return {
            "id": line.id,
            "model": line.model,
            "view_type": line.view_type,
            "label": label,
            "applied": line.applied,
            "view_id": line.view_id.id or False,
            "xml_id": f"{project.module_name}.{line._studio_xml_name()}",
            "changes": len(changes),
        }

    @api.model
    def _project_counts(self, project):
        """{fields, views, views_added, models, access, rules, groups, apps,
        total, edited_views, name_blockers} of the draft of ``project``:
        ``fields`` its
        changes that add a new field, ``views`` its other changes of views,
        ``views_added`` the views it adds,
        ``models``, ``access``, ``rules``, ``groups``, ``apps`` its lines of
        each kind; ``total`` their sum, its ``item_count``; ``edited_views``
        how many views (pending default views included) its changes edit;
        ``name_blockers`` how many technical names of new fields and models
        stop Apply."""
        changes = project.change_ids
        new_fields = project._project_field_changes()
        edited = {
            (
                c.view_id.id,
                c.model_line_id.id,
                c.view_line_id.id,
                c.view_type if c.model_line_id else "",
            )
            for c in changes
        }
        return {
            "fields": len(new_fields),
            "views": len(changes - new_fields),
            "views_added": len(project.view_line_ids),
            "models": len(project.new_model_ids),
            "access": len(project.access_line_ids),
            "rules": len(project.rule_line_ids),
            "groups": len(project.group_line_ids),
            "apps": len(project.app_ids),
            "total": project.item_count,
            "edited_views": len(edited),
            "name_blockers": len(project._studio_field_name_problems())
            + len(project._studio_model_name_problems()),
        }

    @api.model
    def _touched_models(self, project):
        """[{model, name, new, pending, module, chatter, views, fields,
        changes, access, rules}] of the models ``project`` touches, by
        model: those it creates (``new``; ``pending`` until Apply creates
        them) and those its changes, access rows or rules name.
        ``module``: the module that defines a model of the database, False
        for a model of the project; ``chatter``: whether its records have
        the chatter (a model not created yet: whether it will);
        ``views``: [{type, label, view_id}] of its default views the studio
        edits, for a model of the database. ``fields``: its new fields on
        the model [{name, label, ttype, relation, applied}], ``applied``
        once the model has it; ``changes``, ``access``, ``rules``: how many
        of its changes of views, access rows and rules are on the
        model."""
        lines = {line.model: line for line in project.new_model_ids}
        names = (
            set(lines)
            | set(project.change_ids.mapped("model"))
            | set(project.access_line_ids.mapped("model"))
            | set(project.rule_line_ids.mapped("model"))
            | set(project.view_line_ids.mapped("model"))
        )
        # A one2many or a many2one of the project creates its inverse on
        # the comodel.
        for change in project._project_field_changes():
            definition = change._payload().get("field") or {}
            if project._studio_inverse_definition(change.model, definition):
                names.add(definition.get("relation"))
        IrModel = self.env["ir.model"].sudo()
        View = self.env["ir.ui.view"].sudo()
        editable_types = project._view_types()
        labels = self._view_type_labels()
        result = []
        for model in sorted(name for name in names if name):
            line = lines.get(model)
            known = model in self.env
            record = IrModel._get(model)
            if line and not known:
                name = line.name
            else:
                name = record.name or (line.name if line else model)
            existing = set(self.env[model]._fields) if known else set()
            definitions = project._studio_field_definitions(model)
            if line:
                module = False
                chatter = line.chatter
            else:
                # The first xml id of the ir.model names the module that
                # defines the model; the others only extend it.
                module = (
                    self.env["ir.model.data"]
                    .sudo()
                    .search(
                        [("model", "=", "ir.model"), ("res_id", "=", record.id)],
                        order="id",
                        limit=1,
                    )
                    .module
                    if record
                    else False
                ) or False
                # ``is_mail_thread`` exists only once mail is installed.
                chatter = "is_mail_thread" in IrModel._fields and bool(
                    record.is_mail_thread
                )
            views = []
            if known and not line:
                for view_type in editable_types:
                    view_id = View.default_view(model, view_type)
                    added = project._studio_view_line(model, view_type)
                    if view_id or added:
                        views.append(
                            {
                                "type": view_type,
                                "label": labels.get(view_type, view_type),
                                "view_id": view_id or False,
                                "added": bool(added),
                            }
                        )
            result.append(
                {
                    "model": model,
                    "name": name,
                    "new": bool(line),
                    "pending": bool(line) and not known,
                    "module": module,
                    "chatter": chatter,
                    "views": views,
                    "fields": [
                        {
                            "name": field_name,
                            "label": definition.get("field_description") or field_name,
                            "ttype": definition.get("ttype"),
                            "relation": definition.get("relation") or False,
                            "applied": field_name in existing,
                        }
                        for field_name, (definition, _change) in sorted(
                            definitions.items()
                        )
                    ],
                    "changes": len(
                        project.change_ids.filtered(lambda c, m=model: c.model == m)
                    ),
                    "access": len(
                        project.access_line_ids.filtered(
                            lambda a, m=model: a.model == m
                        )
                    ),
                    "rules": len(
                        project.rule_line_ids.filtered(lambda r, m=model: r.model == m)
                    ),
                }
            )
        return result

    @api.model
    def _app_payload(self, app):
        return {
            "id": app.id,
            "name": app.name,
            "icon": app.icon or False,
            "xml_name": app.xml_name,
            "menu_sequence": app.menu_sequence,
            "sequence": app.sequence,
            "applied": app.applied,
            "models": app.model_line_ids.ids,
            "groups": app.group_line_ids.ids,
            "chain": app._studio_chain(),
        }

    @api.model
    def _group_payload(self, group):
        return {
            "id": group.id,
            "app_id": group.app_id.id,
            "name": group.name,
            "xml_name": group.xml_name,
            "comment": group.comment or "",
            "implied": [[g.id, g.name] for g in group.implied_line_ids],
            "implied_groups": [
                [g.id, g.full_name] for g in group.implied_group_ids.sudo()
            ],
            "missing_implied": group._studio_missing_implied_refs(),
            "applied": group.applied,
        }

    @api.model
    def _access_payload(self, line):
        """An access row as the grid shows it; ``applied`` holds the rights
        of the ir.model.access the last Apply made of it ({perm_*}), False
        while no Apply made it: the grid marks the rights the draft
        changes."""
        record = line.project_id._studio_record("ir.model.access", line.xml_name)
        item = {
            "id": line.id,
            "model": line.model,
            "group": (
                [line.group_id.id, line.group_id.full_name] if line.group_id else False
            ),
            **{perm: line[perm] for perm in PERMS},
            "applied": {perm: record[perm] for perm in PERMS} if record else False,
        }
        if line.group_line_id:
            group = line.group_line_id
            item["group_line"] = [group.id, f"{group.app_id.name} / {group.name}"]
        return item

    @api.model
    def _rule_payload(self, rule):
        return {
            "id": rule.id,
            "name": rule.name,
            "model": rule.model,
            "domain": rule.domain_force,
            "groups": [[g.id, g.full_name] for g in rule.group_ids],
            "group_lines": [
                [g.id, f"{g.app_id.name} / {g.name}"] for g in rule.group_line_ids
            ],
            "global_rule": rule.global_rule,
            "missing_groups": rule._studio_missing_group_refs(),
            **{perm: rule[perm] for perm in PERMS},
        }

    @api.model
    def _model_payload(self, line):
        """A model line as the editor shows it; ``views`` holds the ids of
        its default views once applied; ``pending_views`` says which default
        views hold changes recorded before Apply. ``options_applied``:
        {option: whether the applied model has its field};
        ``option_removals``: {option: whether the option is off while its
        own field is still on the model, which the next Apply removes
        (``_studio_option_leaving``)}; ``sort_fields``: [[name, label]] of the fields its default order
        can name (``_studio_sortable_fields``), by label; ``company_rule``:
        [id, name] of the rule line of « Per company », or False."""
        views = line._studio_views() if line.applied else {}
        parent = line.menu_parent_id
        changes = line.project_id.change_ids.filtered(lambda c: c.model_line_id == line)
        sortable = line.project_id._studio_sortable_fields(line)
        leaving = line.project_id._studio_option_leaving(line)
        return {
            "id": line.id,
            "model": line.model,
            "name": line.name,
            "chatter": line.chatter,
            "order": line.order or "",
            "archivable": line.archivable,
            "manual_order": line.manual_order,
            "per_company": line.per_company,
            "company_rule": (
                [line.company_rule_id.id, line.company_rule_id.name]
                if line.company_rule_id
                else False
            ),
            "options_applied": line._studio_options_applied(),
            "option_removals": {
                key: key in leaving for key in studio_arch.MODEL_OPTIONS
            },
            "sort_fields": sorted(
                ([name, label] for name, label in sortable.items()),
                key=lambda item: (item[1].lower(), item[0]),
            ),
            "menu_mode": line.menu_mode,
            "app_id": line.app_id.id,
            "menu_parent": [parent.id, parent.complete_name] if parent else False,
            "menu_name": line.menu_name or "",
            "applied": line.applied,
            "views": {view_type: view.id for view_type, view in views.items()},
            "pending_views": {
                view_type: bool(
                    changes.filtered(lambda c, t=view_type: c.view_type == t)
                )
                for view_type in studio_arch.MODEL_VIEW_TYPES
            },
        }

    @api.model
    def create_project(self, name, module_name):
        """A new project, edited by the user. Return its id."""
        self._check_studio_access()
        project = self.env["erplibre.studio.project"].create(
            {"name": name, "module_name": module_name, "user_id": self.env.uid}
        )
        return project.id

    @api.model
    def _edited_project(self, project_id, revision):
        """The project of an editor call. ``revision`` is the draft revision
        the editor shows: an operation built on another one would locate
        its nodes in a draft that is no longer there."""
        project = self._project(project_id)
        if not project:
            raise UserError(self.env._("Choose or create a studio project first."))
        if revision is not None and int(revision) != project.draft_revision:
            raise UserError(
                self.env._(
                    "The draft of the project changed since this page "
                    "loaded it: reload the editor."
                )
            )
        return project

    @api.model
    def apply_operation(
        self, project_id, model, view_id, view_type, operation, revision=None
    ):
        """Record ``operation`` on the draft; return the new payload.
        ``revision``: see ``_edited_project``."""
        self._check_studio_access()
        project = self._edited_project(project_id, revision)
        view = self._resolve_view(model, view_id, view_type, project)
        project._apply_operation(view, operation or {})
        return self.get_editor_data(model, view.id, view_type, project.id)

    @api.model
    def project_action(
        self,
        project_id,
        action,
        model,
        view_id,
        view_type,
        revision=None,
        fallback=None,
        digest=None,
    ):
        """Run ``action`` (apply, discard, revert, undo, approve, unapprove)
        on the project; return the new payload, with the ``notice`` of the
        action when it answered a notification. ``digest``: the digest of
        the report the user confirmed, for Apply and Revert. When the action
        removed the model or the view on screen (a model of the project),
        the payload is the one of ``fallback`` ([model, view id, view type],
        the view the editor was opened on) with ``view_changed``; without
        such a view left, only {view_gone, project, notice}. A view of a
        model not created yet that Apply created is answered as the view it
        became."""
        self._check_studio_access()
        if action not in PROJECT_ACTIONS:
            raise UserError(self.env._("Unknown action %(action)s.", action=action))
        project = self._edited_project(project_id, revision)
        view = self._resolve_view(model, view_id, view_type, project)
        # A view the project adds stays on screen through Apply and Revert:
        # its line resolves to the view Apply creates, or back to the draft.
        added = project._studio_view_line_of(view)
        if action == "action_undo":
            result = project.action_undo(view)
        elif action in DIGEST_ACTIONS:
            result = getattr(project, action)(digest=digest)
        else:
            result = getattr(project, action)()
        if is_pending_view(view):
            alive = model in self.env or bool(project._studio_pending_line(model))
            view_id = False
        elif added.exists() and model in self.env:
            alive = True
            view_id = False
        elif is_added_view(view):
            alive = bool(self.env["ir.ui.view"].default_view(model, view_type))
            view_id = False
        else:
            alive = model in self.env and bool(view.exists())
            view_id = view.id
        if alive:
            data = self.get_editor_data(model, view_id, view_type, project.id)
        else:
            data = self._fallback_data(project, fallback)
        if isinstance(result, dict) and result.get("tag") == "display_notification":
            data["notice"] = result["params"]["message"]
        return data

    @api.model
    def _fallback_data(self, project, fallback):
        """The payload of the view ``fallback`` [model, view id, view type]
        flagged ``view_changed``, or {view_gone, project} when it is gone
        too."""
        model, view_id, view_type = (list(fallback or []) + [False] * 3)[:3]
        if model and (model in self.env or project._studio_pending_line(model)):
            try:
                data = self.get_editor_data(
                    model, view_id, view_type or "form", project.id
                )
                data["view_changed"] = True
                return data
            except UserError:
                pass
        return {"view_gone": True, "project": self._project_payload(project)}

    @api.model
    def _registry_models(self):
        """[[model, name]] of the models of the registry that store records."""
        records = self.env["ir.model"].sudo().search([("transient", "=", False)])
        return [
            [r.model, r.name]
            for r in records
            if r.model in self.env and not self.env[r.model]._abstract
        ]

    @api.model
    def _pending_models(self, project_id):
        """[[model, name]] of the models of the project not created yet."""
        Project = self.env["erplibre.studio.project"]
        project = Project.browse(int(project_id)).exists() if project_id else Project
        return [
            [line.model, line.name]
            for line in project.new_model_ids
            if line.model not in self.env
        ]

    @api.model
    def get_comodels(self, project_id=False):
        """[[model, name]] of the models a many2one can point to: those of
        the registry, and the models of the project ``project_id`` that
        Apply creates first."""
        self._check_studio_access()
        return self._registry_models() + self._pending_models(project_id)

    # ── models, access rights and rules ─────────────────────────────────

    @api.model
    def get_studio_choices(self, project_id=False):
        """What the dialogs of the models, the access grid and the rules
        offer: the menus a model can go under (with an external id, no
        action, outside the project), the groups (with an external id and
        their ``category`` [id, name]; then the groups of the project,
        ``project`` true, by ``line_id``, ``applied`` once created), the
        apps of the project and the icons of an app, the models rights can
        name, and the model names a new model cannot take
        (``taken_models``)."""
        self._check_studio_access()
        Project = self.env["erplibre.studio.project"]
        project = Project.browse(int(project_id)).exists() if project_id else Project
        Menu = (
            self.env["ir.ui.menu"].sudo().with_context(**{"ir.ui.menu.full_list": True})
        )
        menus = Menu.search([]) - project.created_menu_ids
        menu_xmlids = menus.get_external_id()
        groups = self.env["res.groups"].sudo().search([])
        group_xmlids = groups.get_external_id()
        return {
            "mail_available": Project._studio_mail_available(),
            "icons": Project._studio_app_icons(),
            "menus": sorted(
                (
                    {
                        "id": menu.id,
                        "name": menu.complete_name,
                        "xml_id": menu_xmlids[menu.id],
                    }
                    for menu in menus
                    if menu_xmlids.get(menu.id) and not menu.action
                ),
                key=lambda m: m["name"].lower(),
            ),
            "groups": sorted(
                (
                    {
                        "id": group.id,
                        "name": group.full_name,
                        "xml_id": group_xmlids[group.id],
                        "category": (
                            [group.category_id.id, group.category_id.name]
                            if group.category_id
                            else False
                        ),
                    }
                    for group in groups - project.created_group_ids
                    if group_xmlids.get(group.id)
                ),
                key=lambda g: g["name"].lower(),
            )
            + [
                {
                    "id": False,
                    "line_id": line.id,
                    "name": f"{line.app_id.name} / {line.name}",
                    "xml_id": f"{project.module_name}.{line.xml_name}",
                    "project": True,
                    # A view names the group once Apply has created it.
                    "applied": line.applied,
                }
                for line in project.group_line_ids
            ],
            "apps": [
                {
                    "id": app.id,
                    "name": app.name,
                    "icon": app.icon or False,
                    "xml_name": app.xml_name,
                }
                for app in project.app_ids
            ],
            "models": [
                item for item in self._registry_models() if not protected_model(item[0])
            ]
            + self._pending_models(project.id),
            "taken_models": sorted(Project._studio_taken_models()),
        }

    @api.model
    def _answer(self, project, model, view_id, view_type, **extra):
        data = self.get_editor_data(model, view_id, view_type, project.id)
        data.update(extra)
        return data

    @api.model
    def create_model(
        self, project_id, values, model, view_id, view_type, revision=None
    ):
        """Add a model to the project (see ``_studio_create_model``); the
        payload of the current view, with ``created_model``."""
        self._check_studio_access()
        project = self._edited_project(project_id, revision)
        view = self._resolve_view(model, view_id, view_type, project)
        line = project._studio_create_model(values or {})
        return self._answer(
            project,
            model,
            view.id,
            view_type,
            created_model=self._model_payload(line),
        )

    @api.model
    def update_model(
        self, project_id, line_id, values, model, view_id, view_type, revision=None
    ):
        self._check_studio_access()
        project = self._edited_project(project_id, revision)
        view = self._resolve_view(model, view_id, view_type, project)
        project._studio_update_model(project._studio_model_line(line_id), values or {})
        return self._answer(project, model, view.id, view_type)

    @api.model
    def remove_model(
        self, project_id, line_id, model, view_id, view_type, revision=None
    ):
        self._check_studio_access()
        project = self._edited_project(project_id, revision)
        view = self._resolve_view(model, view_id, view_type, project)
        project._studio_remove_model(project._studio_model_line(line_id))
        return self._answer(project, model, view.id, view_type)

    @api.model
    def add_view(self, project_id, model, view_type, revision=None):
        """Add the ``view_type`` view of ``model``, which has none, to the
        draft (see ``_studio_add_view``); the payload of that view, the
        editor opens it."""
        self._check_studio_access()
        project = self._edited_project(project_id, revision)
        project._studio_add_view(model, view_type)
        return self.get_editor_data(model, False, view_type, project.id)

    @api.model
    def remove_view(
        self,
        project_id,
        line_id,
        model,
        view_id,
        view_type,
        revision=None,
        fallback=None,
    ):
        """Take the view of the view line ``line_id`` out of the draft (see
        ``_studio_remove_view``). The payload of the view on screen; when it
        was that view and Apply had not created it, the payload of
        ``fallback`` ([model, view id, view type]), else of the first view
        of the model the editor opens, flagged ``view_changed``; without
        one, {view_gone, project}."""
        self._check_studio_access()
        project = self._edited_project(project_id, revision)
        project._studio_remove_view(project._studio_added_line(line_id))
        try:
            return self.get_editor_data(model, view_id, view_type, project.id)
        except UserError:
            pass
        data = self._fallback_data(project, fallback)
        if not data.get("view_gone") or model not in self.env:
            return data
        View = self.env["ir.ui.view"].sudo()
        for other in project._view_types():
            if View.default_view(model, other):
                data = self.get_editor_data(model, False, other, project.id)
                data["view_changed"] = True
                return data
        return data

    @api.model
    def update_app(self, project_id, values, model, view_id, view_type, revision=None):
        """Rename the first app of the project or change its icon (an editor
        of a single app); ``save_app`` edits any app."""
        self._check_studio_access()
        project = self._edited_project(project_id, revision)
        view = self._resolve_view(model, view_id, view_type, project)
        project._studio_update_app(values or {})
        return self._answer(project, model, view.id, view_type)

    @api.model
    def set_access(self, project_id, rows, model, view_id, view_type, revision=None):
        """Replace the access rows of the project (``_studio_set_access``)."""
        self._check_studio_access()
        project = self._edited_project(project_id, revision)
        view = self._resolve_view(model, view_id, view_type, project)
        project._studio_set_access(rows or [])
        return self._answer(project, model, view.id, view_type)

    @api.model
    def save_rule(self, project_id, rule, model, view_id, view_type, revision=None):
        """Create or update a rule of the project (``_studio_save_rule``)."""
        self._check_studio_access()
        project = self._edited_project(project_id, revision)
        view = self._resolve_view(model, view_id, view_type, project)
        line = project._studio_save_rule(rule or {})
        return self._answer(project, model, view.id, view_type, saved_rule=line.id)

    @api.model
    def remove_rule(
        self, project_id, rule_id, model, view_id, view_type, revision=None
    ):
        self._check_studio_access()
        project = self._edited_project(project_id, revision)
        view = self._resolve_view(model, view_id, view_type, project)
        project._studio_remove_rule(project._studio_rule_line(rule_id))
        return self._answer(project, model, view.id, view_type)

    @api.model
    def save_geo_layer(
        self, project_id, values, model, view_id, view_type, revision=None
    ):
        """Create or update a vector layer of the GeoEngine view on screen
        (``_studio_save_geo_layer``); the payload with ``saved_geo_layer``."""
        self._check_studio_access()
        project = self._edited_project(project_id, revision)
        view = self._resolve_view(model, view_id, view_type, project)
        line = project._studio_geo_line(view)
        layer = project._studio_save_geo_layer(line, values or {})
        return self._answer(
            project, model, view.id, view_type, saved_geo_layer=layer.id
        )

    @api.model
    def remove_geo_layer(
        self, project_id, layer_id, model, view_id, view_type, revision=None
    ):
        """Remove a layer of the GeoEngine view on screen
        (``_studio_remove_geo_layer``)."""
        self._check_studio_access()
        project = self._edited_project(project_id, revision)
        view = self._resolve_view(model, view_id, view_type, project)
        line = project._studio_geo_line(view)
        project._studio_remove_geo_layer(project._studio_geo_layer(line, layer_id))
        return self._answer(project, model, view.id, view_type)

    @api.model
    def check_rule_domain(self, project_id, model, domain):
        """{ok, count} when ``domain`` applies to ``model`` as a record
        rule, ``count`` the records it matches (False for a model not
        created yet, or one whose option fields Apply has not created yet);
        else {ok: False, error}."""
        self._check_studio_access()
        # A read: the project is not opened, its editor and its revision
        # stay as they are.
        Project = self.env["erplibre.studio.project"]
        project = Project.browse(int(project_id or 0)).exists()
        if not project:
            raise UserError(self.env._("Choose or create a studio project first."))
        try:
            project._studio_check_rights_model(model)
            terms = project._studio_rule_domain(model, domain)
        except UserError as exc:
            return {"ok": False, "error": str(exc.args[0])}
        count = False
        if model in self.env and not project._studio_pending_option_fields(model):
            count = self.env[model].sudo().search_count(terms)
        return {"ok": True, "count": count}

    @api.model
    def get_access_existing(self, project_id, model):
        """The access rights of ``model`` the project did not create:
        [{id, name, group, perm_*, module}], to show next to its grid."""
        self._check_studio_access()
        Project = self.env["erplibre.studio.project"]
        project = Project.browse(int(project_id)).exists() if project_id else Project
        if model not in self.env:
            return []
        rows = (
            self.env["ir.model.access"].sudo().search([("model_id.model", "=", model)])
            - project.created_access_ids
        )
        xmlids = rows.get_external_id()
        return [
            {
                "id": row.id,
                "name": row.name,
                "group": (
                    [row.group_id.id, row.group_id.full_name] if row.group_id else False
                ),
                "module": (xmlids.get(row.id) or "").split(".")[0] or False,
                **{perm: row[perm] for perm in PERMS},
            }
            for row in rows
        ]

    # ── apps and groups ─────────────────────────────────────────────────

    @api.model
    def save_app(self, project_id, values, model, view_id, view_type, revision=None):
        """Create or update an app of the project (``_studio_save_app``); the
        payload with ``saved_app``."""
        self._check_studio_access()
        project = self._edited_project(project_id, revision)
        view = self._resolve_view(model, view_id, view_type, project)
        app = project._studio_save_app(values or {})
        return self._answer(project, model, view.id, view_type, saved_app=app.id)

    @api.model
    def remove_app(self, project_id, app_id, model, view_id, view_type, revision=None):
        """Remove an app of the project: refused while a model or a group
        goes in it."""
        self._check_studio_access()
        project = self._edited_project(project_id, revision)
        view = self._resolve_view(model, view_id, view_type, project)
        project._studio_remove_app(project._studio_app_line(app_id))
        return self._answer(project, model, view.id, view_type)

    @api.model
    def save_group(self, project_id, values, model, view_id, view_type, revision=None):
        """Create or update a group of the project (``_studio_save_group``);
        the payload with ``saved_group``."""
        self._check_studio_access()
        project = self._edited_project(project_id, revision)
        view = self._resolve_view(model, view_id, view_type, project)
        group = project._studio_save_group(values or {})
        return self._answer(project, model, view.id, view_type, saved_group=group.id)

    @api.model
    def remove_group(
        self, project_id, group_id, model, view_id, view_type, revision=None
    ):
        """Remove a group of the project with its access rows; the rules and
        the groups that named it lose it."""
        self._check_studio_access()
        project = self._edited_project(project_id, revision)
        view = self._resolve_view(model, view_id, view_type, project)
        project._studio_remove_group(project._studio_group_line(group_id))
        return self._answer(project, model, view.id, view_type)

    @api.model
    def _members_limit(self, limit):
        """``limit`` as a count of members to name: MEMBERS_SHOWN by
        default, between 1 and 100."""
        return max(1, min(int(limit or MEMBERS_SHOWN), 100))

    @api.model
    def _users_payload(self, users, limit):
        """{count, users: [{id, name}], more} of the res.users ``users``:
        the first ``limit`` by name, ``more`` when there are others."""
        users = users.sorted(lambda u: ((u.name or "").lower(), u.id))
        return {
            "count": len(users),
            "users": [{"id": u.id, "name": u.name} for u in users[:limit]],
            "more": len(users) > limit,
        }

    @api.model
    def _members_payload(self, group, limit):
        """``_users_payload`` of the members of the res.groups ``group``; a
        named member is ``direct`` when none of their other groups implies
        ``group``, else they hold it through an implication."""
        data = self._users_payload(group.users, limit)
        users = self.env["res.users"].sudo().browse([u["id"] for u in data["users"]])
        for item, user in zip(data["users"], users, strict=True):
            item["direct"] = not any(
                group in other.trans_implied_ids for other in user.groups_id - group
            )
        return data

    @api.model
    def get_group_members(
        self, project_id=False, group_ids=None, line_ids=None, limit=MEMBERS_SHOWN
    ):
        """The active members of groups, at most ``limit`` named of each
        (``_members_payload``): {groups: [{id, name, xml_id, category,
        implied, count, users, more}] for the res.groups ``group_ids``,
        ``category`` [id, name] or False and ``implied`` [[id, name]] the
        groups it implies; lines: [{line_id, applied, count, users, more}]
        for the groups ``line_ids`` of the project ``project_id``}, a group
        of the project having members once Apply made it. A read."""
        self._check_studio_access()
        limit = self._members_limit(limit)
        Groups = self.env["res.groups"].sudo()
        result = {"groups": [], "lines": []}
        for group in Groups.browse([int(i) for i in group_ids or []]).exists():
            category = group.category_id
            result["groups"].append(
                {
                    "id": group.id,
                    "name": group.full_name,
                    "xml_id": group.get_external_id().get(group.id) or False,
                    "category": [category.id, category.name] if category else False,
                    "implied": [[g.id, g.full_name] for g in group.implied_ids],
                    **self._members_payload(group, limit),
                }
            )
        if line_ids:
            project = self._read_project(project_id)
            for line_id in line_ids:
                line = project._studio_group_line(line_id)
                record = line._studio_group_record()
                members = (
                    self._members_payload(record, limit)
                    if record
                    else {"count": 0, "users": [], "more": False}
                )
                result["lines"].append(
                    {"line_id": line.id, "applied": bool(record), **members}
                )
        return result

    @api.model
    def get_group_losses(self, project_id, limit=MEMBERS_SHOWN):
        """What the next Apply takes from members of the groups of the
        project ``project_id`` (``_studio_group_losses``): [{group,
        line_id, via, via_line_id, count, users, more}], one entry per
        group of the project ``via`` that no longer implies the group of the
        project ``group`` in the draft and whose members lose ``group``;
        ``group`` and ``via`` are [res.groups id, name], ``line_id`` and
        ``via_line_id`` their groups of the project; at most ``limit``
        members named. A read."""
        self._check_studio_access()
        limit = self._members_limit(limit)
        project = self._read_project(project_id)
        lines = {}
        for line in project.group_line_ids:
            record = line._studio_group_record()
            if record:
                lines[record.id] = line.id
        result = []
        for record, dropped, users in project._studio_group_losses():
            if not users:
                continue
            result.append(
                {
                    "group": [dropped.id, dropped.full_name],
                    "line_id": lines.get(dropped.id, False),
                    "via": [record.id, record.full_name],
                    "via_line_id": lines.get(record.id, False),
                    **self._users_payload(users, limit),
                }
            )
        return result

    # ── relations ───────────────────────────────────────────────────────

    @api.model
    def get_relation_choices(
        self, project_id, model, comodel, ttype="one2many", label=None
    ):
        """What the dialog of a new one2many or many2many of ``model`` to
        ``comodel`` offers: {inverses: [{name, label, pending}],
        inverse_name, inverse_label, on_delete, protected} for a one2many
        (the inverse many2one to choose, else the one the studio creates),
        {relation_table, column1, column2} for a many2many labelled
        ``label``. A read."""
        self._check_studio_access()
        project = self._read_project(project_id)
        known = model in self.env or project._studio_pending_line(model)
        if not known:
            raise UserError(self.env._("Unknown model %(model)s.", model=model))
        comodel = project._clean_relation({"relation": comodel})
        if ttype == "many2many":
            table, column1, column2 = studio_arch.many2many_names(
                project.module_name,
                model,
                comodel,
                project._studio_proposed_field_name(model, comodel, label),
                project._studio_relation_table_names(),
            )
            return {
                "relation_table": table,
                "column1": column1,
                "column2": column2,
            }
        name, label = project._studio_proposed_inverse(model, comodel)
        return {
            "inverses": project._studio_inverse_choices(model, comodel),
            "inverse_name": name,
            "inverse_label": label,
            "on_delete": (
                "cascade" if comodel in project._studio_new_models() else "set null"
            ),
            "protected": protected_model(comodel),
        }

    @api.model
    def check_field_name(self, project_id, model, name, field_name=False, label=False):
        """What the technical name ``name`` of a new field of ``model`` gives:
        {name, proposed, status, message, detail, checks, rule}.
        ``field_name``: the current name of the field of the project being
        renamed, which the checks leave aside. ``proposed``: the name its
        label ``label`` proposes (the label of ``field_name`` when none),
        or False. ``status``: « available », « taken » or « invalid ».
        ``rule``: ``_studio_field_name_rule``. An empty ``name`` checks the
        proposed one. A read."""
        self._check_studio_access()
        project = self._read_project(project_id)
        if not (model in self.env or project._studio_pending_line(model)):
            raise UserError(self.env._("Unknown model %(model)s.", model=model))
        own = field_name or None
        # The field renamed: a field of the project on ``model``, or an
        # inverse field another field of the project creates on it.
        definition, owner = project._studio_field_definitions(model).get(
            own, ({}, None)
        )
        label = label or definition.get("field_description")
        proposed = False
        if label:
            taken = project._taken_field_names(model) - {own}
            inverse = owner and not (owner.model == model and owner.field_name == own)
            if inverse and definition.get("ttype") == "one2many":
                # The inverse one2many of a many2one: « x_<label>_ids ».
                proposed = project._studio_inverse_o2m_name(label, taken)
            else:
                proposed = studio_arch.field_name_from_label(label, taken)
        name = (name or "").strip() or proposed or ""
        status = project._studio_field_name_status(model, name, own)
        if status["code"] is None:
            state = "available"
        elif status["code"] == "unique":
            state = "taken"
        else:
            state = "invalid"
        return {
            "name": name,
            "proposed": proposed,
            "status": state,
            "message": status["message"],
            "detail": status["detail"],
            "checks": status["checks"],
            "rule": project._studio_field_name_rule(),
        }

    @api.model
    def check_model_name(self, project_id, name, line_id=False, label=False):
        """What the technical name ``name`` of a new model gives: {name,
        proposed, status, message, detail, checks, rule}. ``line_id``: the
        model line of the project being renamed, which the checks leave
        aside. ``proposed``: the ``x_`` name its label ``label`` proposes
        (the label of the line when none), or False. ``status``:
        « available », « taken » or « invalid ». ``rule``:
        ``_studio_model_name_rule``. An empty ``name`` checks the proposed
        one. A read."""
        self._check_studio_access()
        project = self._read_project(project_id)
        line = project._studio_model_line(line_id) if line_id else None
        label = label or (line.name if line else False)
        proposed = False
        if label:
            taken = project._studio_taken_models() - {line.model if line else None}
            proposed = studio_arch.model_name_from_label(label, taken)
        name = (name or "").strip() or proposed or ""
        status = project._studio_model_name_status(name, line)
        if status["code"] is None:
            state = "available"
        elif status["code"] == "unique":
            state = "taken"
        else:
            state = "invalid"
        return {
            "name": name,
            "proposed": proposed,
            "status": state,
            "message": status["message"],
            "detail": status["detail"],
            "checks": status["checks"],
            "rule": project._studio_model_name_rule(),
        }

    # ── confirmations ───────────────────────────────────────────────────

    @api.model
    def get_revert_report(self, project_id):
        """{report, digest, refused}: what Revert removes, the digest Revert
        then asks, and why it is refused (or False). A read."""
        self._check_studio_access()
        return self._read_project(project_id)._studio_revert_report()

    @api.model
    def get_apply_report(self, project_id):
        """{report, digest, confirm}: what Apply removes; ``confirm`` when it
        holds records, values or group members, and Apply then asks the
        digest. A read."""
        self._check_studio_access()
        return self._read_project(project_id)._studio_apply_report()

    @api.model
    def get_option_removal_report(self, project_id, line_id, key):
        """{report, refused, waiting}: what turning the option ``key`` of the
        model line ``line_id`` off removes at the next Apply, with its
        effects on the records, why that removal is refused (or False),
        and whether it waits for the installed generated module
        (``_studio_option_removal_report``). A read."""
        self._check_studio_access()
        if key not in studio_arch.MODEL_OPTIONS:
            raise UserError(self.env._("Unknown model option %(key)s.", key=key))
        project = self._read_project(project_id)
        line = project._studio_model_line(line_id)
        return project._studio_option_removal_report(line, key)

    # ── preview of a model not created yet ──────────────────────────────

    @api.model
    def get_model_preview(
        self, project_id, line_id, view_type="form", mode="simulation"
    ):
        """The preview of the model line ``line_id``, not created yet, in the
        shape of get_views: « simulation » computes it from the draft and
        writes nothing; « real », once the project is approved, renders it
        from the model created in a savepoint, then rolled back. Not a
        readonly call: the real mode needs a cursor that writes."""
        self._check_studio_access()
        if mode not in PREVIEW_MODES:
            raise UserError(self.env._("Unknown preview mode %(mode)s.", mode=mode))
        if view_type not in studio_arch.MODEL_VIEW_TYPES:
            raise UserError(
                self.env._(
                    "Apply the model first: %(type)s needs its records.",
                    type=view_type,
                )
            )
        project = self._read_project(project_id)
        line = project._studio_model_line(line_id)
        if line.applied:
            raise UserError(
                self.env._(
                    "The model %(model)s exists: its preview is the one of its "
                    "views.",
                    model=line.model,
                )
            )
        if mode == "real":
            data = project._studio_real_views(line)
        else:
            data = project._studio_simulated_views(line)
        data["view_type"] = view_type
        return data
