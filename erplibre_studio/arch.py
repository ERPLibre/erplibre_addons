# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""View architecture helpers of the studio editor.

A studio change becomes one inheritance spec applied to the combined arch
of a view. Each node shown by the editor carries an XPath that locates it
in the arch as it stands when the next change applies: the combined arch
with the earlier changes of the project already applied. Changes apply in
their sequence, so a recorded XPath keeps pointing at the same node.

Every function here works on lxml elements and plain dicts: what needs
the models of the database (field types, the view types installed) is
the part of the project and the editor.
"""

import copy
import re
import unicodedata

from lxml import etree
from odoo.tools.template_inheritance import apply_inheritance_specs

# « timeline » exists only when web_timeline adds it to ir.ui.view.type:
# the editor offers the view types of this tuple that the registry knows.
VIEW_TYPES = ("form", "list", "kanban", "search", "pivot", "timeline")
POSITIONS = ("before", "after", "inside")

# The QWeb views: their fields show from a template under <templates>.
TEMPLATED_TYPES = ("kanban", "timeline")
# The template elements a node can be dropped into.
TEMPLATE_DROPS = ("t", "main", "aside", "footer", "header", "div", "section")
# The QWeb directives that replace or ignore the body of their element: the
# body of a t-esc or a t-out shows only for an empty value, a t-set with a
# value and a t-call do not render it. A node dropped into one never shows.
CONTENT_DIRECTIVES = (
    "t-esc",
    "t-out",
    "t-raw",
    "t-field",
    "t-set",
    "t-value",
    "t-valuef",
    "t-call",
    "t-call-assets",
)

# The elements the editor lays out with their children; a node dropped
# « inside » one of DROP_CONTAINERS lands at its end. In a templated view,
# the TEMPLATE_DROPS count only under <templates>.
CONTAINERS = {
    "form": (
        "form",
        "sheet",
        "header",
        "footer",
        "group",
        "notebook",
        "page",
        "div",
    ),
    "list": ("list",),
    "kanban": ("kanban", "templates") + TEMPLATE_DROPS,
    "search": ("search", "group"),
    "pivot": ("pivot",),
    "timeline": ("timeline", "templates") + TEMPLATE_DROPS,
}
DROP_CONTAINERS = {
    "form": ("sheet", "group", "page", "div"),
    "list": ("list",),
    "kanban": TEMPLATE_DROPS,
    "search": ("search", "group"),
    "pivot": ("pivot",),
    "timeline": ("timeline",) + TEMPLATE_DROPS,
}

# How a view type hides a node: an attribute, or the node removed from the
# arch (a filter or a pivot field has no « invisible » of its own).
HIDE_MODES = {
    "form": "invisible",
    "list": "column_invisible",
    "kanban": "invisible",
    "timeline": "invisible",
    "search": "remove",
    "pivot": "remove",
}

# The node attributes the editor shows; ``settable`` ones are added.
SHOWN_ATTRS = (
    "string",
    "invisible",
    "column_invisible",
    "required",
    "readonly",
    "optional",
    "widget",
    "groups",
    "help",
    "class",
    "name",
    "domain",
    "filter_domain",
    "context",
    "operator",
    "type",
    "interval",
    "title",
    "bg_color",
    "t-name",
    "t-if",
    "t-elif",
    "t-else",
)

# Change type -> node attribute; « hide » depends on the view type.
ATTRIBUTE_CHANGES = {
    "relabel": "string",
    "required": "required",
    "readonly": "readonly",
    "help": "help",
    "optional": "optional",
}
BOOLEAN_CHANGES = ("hide", "required", "readonly")
ADD_CHANGES = ("add_field", "add_existing_field")
CHANGE_TYPES = (
    ADD_CHANGES
    + ("add_node", "move", "hide", "remove", "set_attribute")
    + tuple(ATTRIBUTE_CHANGES)
)

# The editor operations each view type accepts.
VIEW_OPERATIONS = {
    "form": (
        "add_field",
        "add_existing_field",
        "move",
        "remove",
        "hide",
        "relabel",
        "required",
        "readonly",
        "help",
        "update_field",
    ),
    "list": (
        "add_field",
        "add_existing_field",
        "move",
        "remove",
        "hide",
        "relabel",
        "required",
        "readonly",
        "help",
        "optional",
        "update_field",
    ),
    "kanban": (
        "add_field",
        "add_existing_field",
        "add_widget",
        "move",
        "remove",
        "hide",
        "set_attribute",
        "update_field",
    ),
    "search": (
        "add_existing_field",
        "add_filter",
        "add_group_by",
        "add_separator",
        "move",
        "remove",
        "hide",
        "relabel",
    ),
    "pivot": (
        "add_existing_field",
        "move",
        "remove",
        "hide",
        "relabel",
        "set_attribute",
    ),
    "timeline": (
        "add_existing_field",
        "move",
        "remove",
        "hide",
        "set_attribute",
    ),
}

# The attributes « set_attribute » may write: view type -> tag ->
# attribute -> kind of value. The kind says how the value is checked.
SETTABLE_ATTRIBUTES = {
    "kanban": {
        "kanban": {
            "default_group_by": "group_field",
            "default_order": "order",
            "quick_create": "bool",
            "group_create": "bool",
            "group_delete": "bool",
            "group_edit": "bool",
            "records_draggable": "bool",
            "archivable": "bool",
        },
        "field": {"widget": "widget"},
    },
    "pivot": {
        "pivot": {
            "disable_linking": "bool",
            "display_quantity": "bool",
        },
        "field": {"type": "axis", "interval": "interval"},
    },
    "timeline": {
        "timeline": {
            "date_start": "date_field",
            "date_stop": "date_field",
            "date_delay": "number_field",
            # web_timeline makes a row of a many2one or a many2many only:
            # any other value puts every item in one row.
            "default_group_by": "relation_group_field",
            "colors": "colors",
            "mode": "timeline_mode",
            "stack": "bool",
            "event_open_popup": "bool",
        },
    },
}
# The settable attributes a view needs: they can change, not go away.
REQUIRED_ATTRIBUTES = {
    ("timeline", "timeline"): ("date_start", "default_group_by"),
}

PIVOT_AXES = ("row", "col", "measure")
INTERVALS = ("day", "week", "month", "quarter", "year")
TIMELINE_MODES = ("day", "week", "month", "fit")
DATE_TYPES = ("date", "datetime")
NUMBER_TYPES = ("integer", "float", "monetary")
# The fields web_timeline groups its items by, one row per record.
RELATION_TYPES = ("many2one", "many2many")

# The widgets « add_widget » puts in a kanban card, with the attributes
# each one takes.
WIDGETS = {
    "web_ribbon": ("title", "bg_color", "tooltip"),
}

# The domain operators of a search filter, by field type. « set » and
# « not set » compare with False.
SEARCH_OPERATORS = {
    "char": ("ilike", "not ilike", "=", "!=", "set", "not set"),
    "text": ("ilike", "not ilike", "set", "not set"),
    "html": ("ilike", "not ilike", "set", "not set"),
    "integer": ("=", "!=", ">", ">=", "<", "<=", "set", "not set"),
    "float": ("=", "!=", ">", ">=", "<", "<=", "set", "not set"),
    "monetary": ("=", "!=", ">", ">=", "<", "<=", "set", "not set"),
    "boolean": ("=", "!="),
    "date": ("=", "!=", ">", ">=", "<", "<=", "set", "not set"),
    "datetime": ("=", "!=", ">", ">=", "<", "<=", "set", "not set"),
    "selection": ("=", "!=", "set", "not set"),
    # A many2one compares by name: a record id would tie the filter to the
    # database it was made in.
    "many2one": ("ilike", "not ilike", "set", "not set"),
    "many2many": ("ilike", "not ilike", "set", "not set"),
    "one2many": ("ilike", "not ilike", "set", "not set"),
}
# The comparison operators of a timeline color rule.
COLOR_OPERATORS = ("==", "!=", ">", ">=", "<", "<=")
# The field types a color rule compares. web_timeline evaluates the rule on
# the values of search_read: a many2one is [id, name] there, never equal to
# a value. A datetime value holds « : », which ends the rule in the colors
# attribute (« color:expression; »).
COLOR_FIELD_TYPES = (
    "char",
    "text",
    "integer",
    "float",
    "monetary",
    "boolean",
    "date",
    "selection",
)
# The types of field a timeline item shows. Its template renders with the
# values of search_read and no record of a kanban: a <field> does not
# compile there, the item shows ``record.<name>``, a many2one by its name.
ITEM_FIELD_TYPES = COLOR_FIELD_TYPES + ("datetime", "many2one")
# How an item shows a value of search_read: « many2one », its name;
# « raw », as it is (a number, a boolean); « text », nothing for an empty
# value, which search_read gives as False and QWeb prints « false ».
ITEM_KINDS = ("many2one", "raw", "text")

# The tags « add_node » inserts; the attributes come from the operation.
NODE_TAGS = ("filter", "separator", "widget")

OPTIONAL_VALUES = ("", "show", "hide")

_SAFE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TEMPLATE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")
_FIELD_NAME = re.compile(r"^x_[a-z0-9_]+$")
_MODULE_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
# A node attribute a change may write: never a QWeb directive (« t- »).
_ATTRIBUTE_NAME = re.compile(r"^[a-z_][a-z0-9_]*$")
_CHAIN_ATTRS = ("t-elif", "t-else")
# The value a node of a timeline item shows: « record.x », the name of a
# many2one « record.x and record.x[1] », either one « or '' ».
_ITEM_VALUE = re.compile(
    r"^\s*record\.([A-Za-z_][A-Za-z0-9_]*)"
    r"(?:\s+and\s+record\.\1\[1\])?(?:\s+or\s+'')?\s*$"
)
# The attribute that marks, in a draft arch built to find them, the nodes a
# change added; never written to a view.
ADDED_MARK = "erplibre_studio_added"


class ArchError(ValueError):
    """A change or an operation does not fit the arch. ``code`` and
    ``params`` let the caller build a translated message; ``str()`` is the
    English one."""

    def __init__(self, message, code=None, **params):
        super().__init__(message)
        self.code = code
        self.params = params


def constant_true(value):
    """Whether a node attribute holds a constant true expression; a
    condition (« is_company ») is not one."""
    return value in ("1", "True", "true")


def hide_attribute(view_type):
    """The attribute that hides a node: a whole column in a list."""
    return "column_invisible" if view_type == "list" else "invisible"


def hide_mode(view_type):
    """« invisible », « column_invisible » or « remove »: see HIDE_MODES."""
    return HIDE_MODES[view_type]


def elements(node):
    """The element children of ``node``, without comments."""
    return [child for child in node if isinstance(child.tag, str)]


def _named_expr(node):
    if node.tag == "t":
        name = node.get("t-name")
        if name and _TEMPLATE_NAME.match(name):
            return f"//t[@t-name='{name}']"
        return None
    name = node.get("name")
    if name and _SAFE_NAME.match(name):
        return f"//{node.tag}[@name='{name}']"
    return None


def node_xpath(root, node):
    """An XPath of ``node`` in ``root``: by name (a template by its
    ``t-name``) when the name finds this node first (the inheritance specs
    take the first match), else by position under the nearest such
    ancestor."""
    if node is root:
        return f"/{root.tag}"
    expr = _named_expr(node)
    if expr and root.xpath(expr)[:1] == [node]:
        return expr
    parent = node.getparent()
    same = [child for child in elements(parent) if child.tag == node.tag]
    return f"{node_xpath(root, parent)}/{node.tag}[{same.index(node) + 1}]"


def locate(root, xpath):
    """The first node of ``root`` that ``xpath`` finds; ArchError if none."""
    try:
        nodes = root.xpath(xpath)
    except etree.XPathError as exc:
        raise ArchError(
            f"Invalid XPath {xpath}: {exc}",
            "invalid_xpath",
            xpath=xpath,
            error=str(exc),
        ) from exc
    nodes = [n for n in nodes if isinstance(n, etree._Element)]
    if not nodes:
        raise ArchError(f"No node at {xpath}.", "no_node", xpath=xpath)
    return nodes[0]


# ── QWeb templates ──────────────────────────────────────────────────────


def in_template(node):
    """Whether ``node`` is inside the <templates> of a QWeb view."""
    return any(item.tag == "templates" for item in node.iterancestors())


def is_template(node):
    """Whether ``node`` is a template: a <t t-name> of <templates>."""
    parent = node.getparent()
    return (
        node.tag == "t"
        and bool(node.get("t-name"))
        and parent is not None
        and parent.tag == "templates"
    )


def templates_of(root):
    """{t-name: node} of the templates of ``root``."""
    return {
        node.get("t-name"): node
        for node in root.xpath("./templates/t[@t-name]")
        if is_template(node)
    }


def _next_element(node):
    item = node.getnext()
    while item is not None and not isinstance(item.tag, str):
        item = item.getnext()
    return item


def chain_role(node):
    """« if », « elif » or « else » when ``node`` is part of a QWeb
    conditional chain (a t-if followed by a t-elif or a t-else), else
    None. A chain is read sibling after sibling: nothing may come between
    its nodes, and none of them moves alone."""
    if any(node.get(attr) is not None for attr in _CHAIN_ATTRS):
        return "elif" if node.get("t-elif") is not None else "else"
    following = _next_element(node)
    if node.get("t-if") is not None and following is not None:
        if any(following.get(attr) is not None for attr in _CHAIN_ATTRS):
            return "if"
    return None


def has_content_directive(view_type, node):
    """Whether ``node``, in a template, has one of CONTENT_DIRECTIVES."""
    return (
        view_type in TEMPLATED_TYPES
        and in_template(node)
        and any(node.get(attr) is not None for attr in CONTENT_DIRECTIVES)
    )


def item_kind(ttype):
    """The ITEM_KINDS entry of a field of type ``ttype``."""
    if ttype == "many2one":
        return "many2one"
    return "raw" if ttype in NUMBER_TYPES + ("boolean",) else "text"


def item_value(name, kind):
    """The expression a timeline item shows for the field ``name``, by its
    ``kind`` (ITEM_KINDS)."""
    if not name or not _SAFE_NAME.match(name):
        raise ArchError(f"Invalid field {name}.", "bad_field", field=name)
    if kind not in ITEM_KINDS:
        raise ArchError(f"Invalid field {name}.", "bad_field", field=name)
    value = f"record.{name}"
    if kind == "many2one":
        return f"{value} and {value}[1] or ''"
    return value if kind == "raw" else f"{value} or ''"


def item_field_name(node):
    """The field a node of a timeline item shows: an element whose t-esc or
    t-out is an ``item_value``, or holds only a <t> that is one. None for
    any other node."""
    for attr in ("t-esc", "t-out"):
        match = _ITEM_VALUE.match(node.get(attr) or "")
        if match:
            return match.group(1)
    children = elements(node)
    if (
        node.tag != "t"
        and len(children) == 1
        and children[0].tag == "t"
        and not (node.text or "").strip()
        and not (children[0].tail or "").strip()
    ):
        for attr in ("t-esc", "t-out"):
            match = _ITEM_VALUE.match(children[0].get(attr) or "")
            if match:
                return match.group(1)
    return None


def shown_field_name(view_type, node):
    """The field ``node`` shows: a <field>, or in a timeline template a node
    of ``item_field_name``. None for any other node."""
    if node.tag == "field":
        return node.get("name")
    if view_type == "timeline" and in_template(node):
        return item_field_name(node)
    return None


def template_field_names(view_type, template):
    """The names of the fields the template ``template`` shows."""
    return {
        name
        for node in template.iter(etree.Element)
        for name in [shown_field_name(view_type, node)]
        if name
    }


# ── where a node may go ─────────────────────────────────────────────────


def _drop_container(view_type, node):
    """Whether ``node`` takes children dropped into it."""
    if node.tag not in DROP_CONTAINERS[view_type]:
        return False
    if has_content_directive(view_type, node):
        return False
    if view_type in TEMPLATED_TYPES and node.tag in TEMPLATE_DROPS:
        return in_template(node) or is_template(node)
    return True


def _content_refusal(node):
    return ArchError(
        f"<{node.tag}> replaces its content: nothing dropped into it shows.",
        "content_directive",
        tag=node.tag,
    )


def drop_refusal(view_type, node, position):
    """Why nothing can be dropped at ``position`` of ``node`` (an
    ArchError), or None when it can."""
    if position not in POSITIONS:
        return ArchError(
            f"Unknown position {position}.", "unknown_position", position=position
        )
    if position == "inside":
        if has_content_directive(view_type, node):
            return _content_refusal(node)
        if not _drop_container(view_type, node):
            return ArchError(
                f"Nothing can be dropped inside <{node.tag}>.",
                "no_drop_inside",
                tag=node.tag,
            )
        return None
    parent = node.getparent()
    if parent is not None and has_content_directive(view_type, parent):
        return _content_refusal(parent)
    if parent is None or not _drop_container(view_type, parent) or is_template(node):
        return ArchError("Nothing can be dropped there.", "no_drop")
    # Between two nodes of a QWeb chain, a node would break it.
    if position == "before" and chain_role(node) in ("elif", "else"):
        return ArchError("Nothing can be dropped inside a t-if chain.", "chain")
    if position == "after" and chain_role(node) in ("if", "elif"):
        return ArchError("Nothing can be dropped inside a t-if chain.", "chain")
    return None


def move_refusal(view_type, node):
    """Why ``node`` cannot move (an ArchError), or None when it can."""
    parent = node.getparent()
    if parent is None or node.tag == "templates" or is_template(node):
        return ArchError(f"<{node.tag}> cannot move.", "no_move", tag=node.tag)
    if view_type in TEMPLATED_TYPES:
        if not in_template(node):
            return ArchError(
                "A field the view loads outside its templates cannot move.",
                "outside_template",
            )
        if chain_role(node):
            return ArchError("A node of a t-if chain cannot move.", "chain_move")
    return None


def hide_refusal(view_type, node):
    """Why ``node`` cannot be hidden (an ArchError), or None."""
    if node.getparent() is None:
        return ArchError("The view itself cannot be hidden.", "no_hide_root")
    if view_type in TEMPLATED_TYPES:
        if not in_template(node):
            return ArchError(
                "A field the view loads outside its templates cannot be "
                "hidden: the templates read it.",
                "outside_template",
            )
        if node.tag == "t" or node.tag == "templates":
            return ArchError(f"<{node.tag}> cannot be hidden.", "no_hide", tag=node.tag)
        # A hidden node is left out of the compiled template: the t-elif or
        # the t-else after it loses its t-if, and the template no longer
        # compiles; after a hidden t-elif, the t-else shows in its place.
        if chain_role(node) in ("if", "elif"):
            return ArchError(
                "The t-if or the t-elif of a chain cannot be hidden.", "chain_hide"
            )
    return None


# ── specs ───────────────────────────────────────────────────────────────


def _bool_text(value):
    return "True" if value else "False"


def _check_attribute_name(name):
    if not name or not _ATTRIBUTE_NAME.match(name):
        raise ArchError(
            f"A change cannot write the attribute {name}.",
            "unsafe_attribute",
            attribute=name,
        )


def _set_attributes(node, attrs):
    for key, value in sorted((attrs or {}).items()):
        _check_attribute_name(key)
        node.set(key, str(value))


def _attributes_spec(xpath, attrs):
    """An ``attributes`` spec: an empty value removes the attribute."""
    spec = etree.Element("xpath", expr=xpath, position="attributes")
    for name, value in sorted(attrs.items()):
        _check_attribute_name(name)
        attribute = etree.SubElement(spec, "attribute", name=name)
        if value not in (None, ""):
            attribute.text = str(value)
    return spec


def change_spec(change, view_type):
    """The inheritance spec of ``change``, a dict {type, xpath, position,
    payload}: an ``xpath`` element, or a ``data`` of two when a move also
    changes attributes of the moved node. A new element each call:
    applying a spec moves its children into the arch."""
    ctype = change["type"]
    payload = change.get("payload") or {}
    if ctype not in CHANGE_TYPES:
        raise ArchError(f"Unknown change type {ctype}.", "unknown_change", type=ctype)
    if ctype in ADD_CHANGES or ctype in ("move", "add_node"):
        position = change.get("position") or "after"
        if position not in POSITIONS:
            raise ArchError(
                f"Unknown position {position}.",
                "unknown_position",
                position=position,
            )
        spec = etree.Element("xpath", expr=change["xpath"], position=position)
        if ctype == "move":
            etree.SubElement(spec, "xpath", expr=payload["source"], position="move")
            if payload.get("attrs"):
                # The moved node, located where the move put it.
                data = etree.Element("data")
                data.append(spec)
                data.append(_attributes_spec(payload["attrs_xpath"], payload["attrs"]))
                return data
        elif ctype == "add_node":
            node_def = payload.get("node") or {}
            tag = node_def.get("tag")
            if tag not in NODE_TAGS:
                raise ArchError(
                    f"A change cannot add <{tag}>.", "unknown_node", tag=tag
                )
            _set_attributes(etree.SubElement(spec, tag), node_def.get("attrs"))
        elif payload.get("item"):
            # A field of a timeline item, and the field loaded for it.
            name = payload["field_name"]
            value = item_value(name, payload["item"])
            etree.SubElement(spec, "span", {"name": name, "t-esc": value})
            if payload.get("load"):
                data = etree.Element("data")
                data.append(spec)
                load = etree.SubElement(
                    data, "xpath", expr=f"/{view_type}/templates", position="before"
                )
                etree.SubElement(load, "field", name=name)
                return data
        else:
            node = etree.SubElement(spec, "field", name=payload["field_name"])
            _set_attributes(node, payload.get("node_attrs"))
        return spec
    if ctype == "remove":
        return etree.Element("xpath", expr=change["xpath"], position="replace")
    if ctype == "set_attribute":
        return _attributes_spec(
            change["xpath"], {payload.get("attribute"): payload.get("value")}
        )
    spec = etree.Element("xpath", expr=change["xpath"], position="attributes")
    if ctype == "hide":
        name = hide_attribute(view_type)
    else:
        name = ATTRIBUTE_CHANGES[ctype]
    attribute = etree.SubElement(spec, "attribute", name=name)
    value = payload.get("value")
    if ctype in BOOLEAN_CHANGES:
        attribute.text = _bool_text(value)
    elif value:
        # An empty <attribute> removes the attribute from the node.
        attribute.text = str(value)
    return spec


def _mark_added(spec, key):
    """Mark with ADDED_MARK = ``key`` the nodes ``spec`` inserts."""
    for item in list(spec) if spec.tag == "data" else [spec]:
        if item.get("position") in POSITIONS:
            for child in elements(item):
                if child.tag != "xpath":
                    child.set(ADDED_MARK, str(key))
    return spec


def _apply_one(arch, change, view_type, mark=False):
    """``arch`` with ``change`` applied, a new element; raise when it does
    not apply. ``mark``: see ``_mark_added``."""
    spec = change_spec(change, view_type)
    if mark:
        _mark_added(spec, change["key"])
    return apply_inheritance_specs(copy.deepcopy(arch), spec)


def apply_changes(arch, changes, view_type, message=str, mark=False):
    """Apply ``changes`` (dicts with a ``key``) in order to a copy of
    ``arch``. Return (arch, errors): a change that does not apply is
    skipped and ``errors`` maps its key to the reason, the text that
    ``message`` gives for the exception. ``mark``: the nodes a change adds
    carry ADDED_MARK, its key."""
    arch = copy.deepcopy(arch)
    errors = {}
    for change in changes:
        try:
            arch = _apply_one(arch, change, view_type, mark)
        except Exception as exc:  # noqa: BLE001 - every spec error is reported
            errors[change["key"]] = message(exc)
    return arch, errors


def _added_by(root, xpath, key=None):
    """The ADDED_MARK of the node at ``xpath`` in ``root`` or of its nearest
    marked ancestor; with ``key``, only that mark counts. None when there
    is none or ``xpath`` finds nothing."""
    try:
        node = locate(root, xpath)
    except ArchError:
        return None
    for item in [node, *node.iterancestors()]:
        mark = item.get(ADDED_MARK)
        if mark and (key is None or mark == str(key)):
            return mark
    return None


def added_key(arch, changes, view_type, xpath):
    """The key (as text) of the change of ``changes`` that added the node at
    ``xpath`` of the arch they make from ``arch``, or None for a node of
    the arch itself."""
    marked, _errors = apply_changes(arch, changes, view_type, mark=True)
    try:
        node = locate(marked, xpath)
    except ArchError:
        return None
    return node.get(ADDED_MARK)


def changes_on_added(arch, changes, view_type, key):
    """The keys of the changes after the change ``key`` that locate a node
    it added, or a node inside one: by their XPath or the source of a move,
    in the arch as it stands when each applies."""
    current = copy.deepcopy(arch)
    found, after = [], False
    for change in changes:
        if after:
            paths = (change.get("xpath"), (change.get("payload") or {}).get("source"))
            if any(path and _added_by(current, path, key) for path in paths):
                found.append(change["key"])
        if change["key"] == key:
            after = True
        try:
            current = _apply_one(current, change, view_type, mark=True)
        except Exception:  # noqa: BLE001,S112 - a change that fails is skipped
            continue
    return found


def view_arch(changes, view_type):
    """The arch of the inherited view that holds ``changes``: a <data> of
    their specs, as a string."""
    data = etree.Element("data")
    for change in changes:
        spec = change_spec(change, view_type)
        if spec.tag == "data":
            data.extend(list(spec))
        else:
            data.append(spec)
    return etree.tostring(data, encoding="unicode", pretty_print=True)


def moved_node_xpath(arch, change, view_type):
    """Where the node ``change`` moves ends up: its XPath in ``arch`` once
    the move applied. ``arch`` is left untouched."""
    marked = copy.deepcopy(arch)
    marker = "data-erplibre-studio-moved"
    locate(marked, change["payload"]["source"]).set(marker, "1")
    spec = change_spec(
        dict(change, payload={"source": change["payload"]["source"]}), view_type
    )
    moved = apply_inheritance_specs(marked, spec)
    node = moved.xpath(f"//*[@{marker}]")[0]
    del node.attrib[marker]
    return node_xpath(moved, node)


# ── values built from the editor forms ──────────────────────────────────


def filter_condition(field_name, field_type, operator, value):
    """The domain term of a search filter on ``field_name``; ``value``
    already has the Python type of the field. ArchError when the operator
    does not fit the type."""
    if operator not in SEARCH_OPERATORS.get(field_type, ()):
        raise ArchError(
            f"The operator {operator} does not apply to a {field_type} field.",
            "bad_operator",
            operator=operator,
            type=field_type,
        )
    if operator == "set":
        return (field_name, "!=", False)
    if operator == "not set":
        return (field_name, "=", False)
    return (field_name, operator, value)


def domain_text(terms):
    """The text of a domain of ``terms`` joined by AND, for a view
    attribute."""
    return repr([tuple(term) for term in terms])


def group_by_context(field_name, interval=None):
    """The ``context`` text of a group-by filter."""
    group_by = f"{field_name}:{interval}" if interval else field_name
    return repr({"group_by": group_by})


def group_by_of(node):
    """The ``group_by`` a <filter> context names, or None."""
    text = node.get("context") or ""
    match = re.search(r"""['"]group_by['"]\s*:\s*['"]([^'"]+)['"]""", text)
    return match.group(1) if match else None


_COLOR = re.compile(r"^(#[0-9A-Fa-f]{3,8}|[a-z]+)$")


def colors_text(rules):
    """The ``colors`` attribute of a timeline: « color:expression; » for
    each rule {color, field, operator, value}; ``value`` already has the
    Python type of the field."""
    parts = []
    for rule in rules:
        color = (rule.get("color") or "").strip()
        operator = rule.get("operator") or "=="
        field = rule.get("field") or ""
        if not _COLOR.match(color):
            raise ArchError(f"Invalid color {color}.", "bad_color", color=color)
        if operator not in COLOR_OPERATORS:
            raise ArchError(
                f"Invalid operator {operator}.", "bad_color_operator", operator=operator
            )
        if not _SAFE_NAME.match(field):
            raise ArchError(f"Invalid field {field}.", "bad_field", field=field)
        value = repr(rule.get("value"))
        # web_timeline splits the attribute on « ; », then each rule on its
        # first « : »: neither may come in the expression.
        if ":" in value or ";" in value:
            raise ArchError(
                f"The value {rule.get('value')} cannot be used in a timeline "
                "color: it holds « : » or « ; ».",
                "bad_color_value",
                value=rule.get("value"),
            )
        parts.append(f"{color}:{field} {operator} {value}")
    return ";".join(parts)


def colors_rules(text):
    """[{color, expression}] of a ``colors`` attribute."""
    rules = []
    for part in (text or "").split(";"):
        color, sep, expression = part.partition(":")
        if sep and color.strip():
            rules.append({"color": color.strip(), "expression": expression.strip()})
    return rules


_ORDER_TERM = re.compile(r"^\s*([a-z_][a-z0-9_]*)(\s+(asc|desc))?\s*$", re.I)


def order_fields(text):
    """The field names of an order text (« name asc, id desc »); ArchError
    when it is not one."""
    names = []
    for term in (text or "").split(","):
        match = _ORDER_TERM.match(term)
        if not match:
            raise ArchError(f"Invalid order {text}.", "bad_order", order=text)
        names.append(match.group(1))
    return names


def node_name_from_label(prefix, label, taken):
    """A free node name ``<prefix>_<slug of label>``, not in ``taken``."""
    text = unicodedata.normalize("NFKD", label or "").encode("ascii", "ignore")
    slug = re.sub(r"[^a-z0-9]+", "_", text.decode().lower()).strip("_") or "node"
    base = f"{prefix}_{slug}"[:58].rstrip("_")
    name, count = base, 2
    while name in taken:
        name = f"{base}_{count}"
        count += 1
    return name


def arch_names(root, tag=None):
    """The ``name`` attributes of the nodes of ``root`` (of ``tag``)."""
    nodes = root.iter(tag) if tag else root.iter()
    return {n.get("name") for n in nodes if isinstance(n.tag, str) and n.get("name")}


# ── blocks of the editor ────────────────────────────────────────────────


def node_label(node, fields, view_type=None):
    """The text the editor shows for ``node``; ``fields`` maps field names
    to their description (``fields_get``)."""
    name = shown_field_name(view_type, node)
    if name:
        info = fields.get(name) or {}
        return node.get("string") or info.get("string") or name
    for attr in ("string", "name", "for", "t-name", "title"):
        if node.get(attr):
            return node.get(attr)
    for attr in ("t-if", "t-elif"):
        if node.get(attr) is not None:
            return f"{attr} {node.get(attr)}"[:60]
    if node.get("t-else") is not None:
        return "t-else"
    if node.getparent() is None or elements(node):
        # The text of an element with children is the scattered text of
        # its descendants (« at », « , »): its tag says more.
        return node.tag
    text = " ".join("".join(node.itertext()).split())
    return text[:60] or node.tag


def _shown_attrs(node, view_type):
    names = set(SHOWN_ATTRS)
    for attrs in SETTABLE_ATTRIBUTES.get(view_type, {}).values():
        names.update(attrs)
    return {k: node.get(k) for k in sorted(names) if node.get(k) is not None}


def _is_container(node, view_type, depth):
    if node.tag == "field" or (depth and shown_field_name(view_type, node)):
        return False
    if view_type == "form":
        return node.tag in CONTAINERS["form"] or bool(elements(node))
    if view_type == "list":
        return depth == 0
    if view_type in TEMPLATED_TYPES:
        if depth == 0 or node.tag == "templates" or is_template(node):
            return True
        return in_template(node) and (
            node.tag in TEMPLATE_DROPS or bool(elements(node))
        )
    if view_type == "search":
        return node.tag in CONTAINERS["search"]
    return depth == 0


def _node_kind(node, view_type):
    if node.tag == "field" or shown_field_name(view_type, node):
        return "field"
    if node.tag == "widget":
        return "widget"
    if view_type == "search":
        if node.tag == "filter":
            return "group_by" if group_by_of(node) else "filter"
        if node.tag == "separator":
            return "separator"
    return "other"


def arch_blocks(root, view_type, fields):
    """The editor tree of ``root``: nested dicts {path, tag, kind, label,
    attrs, movable, children, drop, name, ...}, the ``blocks`` of the
    editor payload (``get_editor_data``). In a form, any element with children is a container, so
    that a field inside a title shows; in a QWeb view, any element of a
    template is. A field never shows its sub-views: the editor does not
    descend into an x2many."""

    def walk(node, depth):
        block = {
            "path": node_xpath(root, node),
            "tag": node.tag,
            "label": node_label(node, fields, view_type),
            "attrs": _shown_attrs(node, view_type),
            "movable": depth > 0 and move_refusal(view_type, node) is None,
        }
        if _is_container(node, view_type, depth):
            block["kind"] = "template" if is_template(node) else "container"
            block["drop"] = _drop_container(view_type, node)
            block["children"] = [walk(child, depth + 1) for child in elements(node)]
        else:
            block["kind"] = _node_kind(node, view_type)
        if block["kind"] == "field":
            block["name"] = shown_field_name(view_type, node)
        elif block["kind"] in ("widget", "filter", "group_by"):
            block["name"] = node.get("name")
        if view_type in TEMPLATED_TYPES and depth > 0:
            block["in_template"] = in_template(node)
            block["chain"] = chain_role(node)
            if is_template(node):
                block["template"] = node.get("t-name")
        if block["kind"] == "filter":
            block["domain"] = node.get("domain") or ""
        elif block["kind"] == "group_by":
            block["group_by"] = group_by_of(node)
        if view_type == "pivot" and node.tag == "field":
            block["axis"] = node.get("type") if node.get("type") in PIVOT_AXES else None
            block["interval"] = node.get("interval") or None
        return block

    return walk(root, 0)


def arch_field_names(root):
    """The names of the fields of ``root``, sub-views included."""
    return {node.get("name") for node in root.iter("field") if node.get("name")}


def shown_field_names(root, view_type):
    """The names of the fields a view shows: in a QWeb view, those of its
    templates; a field it only loads can still be dropped into one."""
    if view_type not in TEMPLATED_TYPES:
        return arch_field_names(root)
    return {
        name
        for template in templates_of(root).values()
        for name in template_field_names(view_type, template)
    }


def field_name_from_label(label, taken):
    """A free ``x_`` field name made of ``label``: ASCII, lower case,
    underscores, at most 63 characters, not in ``taken``."""
    text = unicodedata.normalize("NFKD", label or "").encode("ascii", "ignore")
    slug = re.sub(r"[^a-z0-9]+", "_", text.decode().lower()).strip("_") or "field"
    base = f"x_{slug}"[:58].rstrip("_")
    name, count = base, 2
    while name in taken:
        name = f"{base}_{count}"
        count += 1
    return name


def valid_field_name(name):
    return bool(name and len(name) <= 63 and _FIELD_NAME.match(name))


def valid_module_name(name):
    return bool(name and len(name) <= 64 and _MODULE_NAME.match(name))
