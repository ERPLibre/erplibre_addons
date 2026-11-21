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

import ast
import copy
import hashlib
import keyword
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
        "add_group",
        "add_page",
        "add_separator",
        "move",
        "remove",
        "hide",
        "relabel",
        "required",
        "readonly",
        "help",
        "update_field",
        "rename_field",
        "set_attribute",
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
        "rename_field",
        "set_attribute",
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
        "rename_field",
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
# A field of a form or a list takes its widget, the domain of its records
# (a relational field) and the groups it shows for.
FIELD_ADVANCED_ATTRIBUTES = {
    "widget": "widget",
    "domain": "field_domain",
    "groups": "groups",
}
SETTABLE_ATTRIBUTES = {
    "form": {"field": FIELD_ADVANCED_ATTRIBUTES},
    "list": {"field": FIELD_ADVANCED_ATTRIBUTES},
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
NODE_TAGS = ("filter", "separator", "widget", "group", "notebook", "page")
# The tags an added node of NODE_TAGS holds, one level deep: a notebook
# comes with its first page.
NODE_CHILDREN = {"notebook": ("page",)}
# The tags a notebook goes in: a tab of a form holds another notebook.
NOTEBOOK_PARENTS = ("sheet", "page")
# The tags of the sub-view an added x2many field holds (``node_children``).
SUBVIEW_TAGS = ("list", "field")
# The relational field types a project adds; a one2many shows in a form only,
# a many2many in a form (a sub-list), a list or a kanban (tags).
X2MANY_TYPES = ("one2many", "many2many")
# The fields whose records a domain restricts.
RELATIONAL_TYPES = ("many2one",) + X2MANY_TYPES
X2MANY_VIEW_TYPES = {
    "one2many": ("form",),
    "many2many": ("form", "list", "kanban"),
}
# The longest name of a PostgreSQL table.
TABLE_NAME_SIZE = 63
# The longest field name: a column of the table of its model.
FIELD_NAME_SIZE = 63
# The prefixes of the names the ORM keeps for itself: the private attributes
# of a model (« _ »), and the reified group fields of res.users
# (« in_group_<id> », « sel_groups_<ids> »), which the ORM computes from
# the groups and never stores.
RESERVED_FIELD_PREFIXES = ("_", "in_group_", "sel_groups_")

# The leaf elements of a form that stay where the view puts them: the
# chatter is laid out by the web client beside or under the sheet, from
# where it stands in the arch.
FIXED_TAGS = ("chatter",)

# A model the studio creates: « x_ », then a letter. 50 characters keep
# the names built from it (« <model>_<comodel>_rel », « view_<model>_search »,
# its table and their indexes) under the 63 characters of PostgreSQL.
MODEL_NAME_SIZE = 50
# The default views of a model the studio creates.
MODEL_VIEW_TYPES = ("form", "list", "search")

# The options of a model the studio creates: {option: (field name, type,
# label)}. Each one adds one field to the model, which Odoo gives a meaning
# by its name: ``x_active`` archives the records, ``x_sequence`` orders them
# by hand (the handle of the list); ``x_company_id`` gives each record a
# company, which a multi-company record rule reads.
MODEL_OPTIONS = {
    "archivable": ("x_active", "boolean", "Active"),
    "manual_order": ("x_sequence", "integer", "Sequence"),
    "per_company": ("x_company_id", "many2one", "Company"),
}
# {field name: (comodel, on_delete)} of the many2one fields of the options.
MODEL_OPTION_RELATIONS = {"x_company_id": ("res.company", "set null")}
# The domain of the global rule the option « per_company » creates: the
# records of the companies the user works in, and the records of no
# company, which every company shares.
COMPANY_RULE_DOMAIN = (
    "['|', ('x_company_id', '=', False), ('x_company_id', 'in', company_ids)]"
)
# The context of the window action of a model whose option « per_company »
# is on: a record created from it takes the current company of the user.
COMPANY_ACTION_CONTEXT = "{'default_x_company_id': allowed_company_ids[0]}"
# The order of the records of a model whose option « manual_order » is on.
MANUAL_ORDER = "x_sequence asc, id asc"

OPTIONAL_VALUES = ("", "show", "hide")

_SAFE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TEMPLATE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")
# A field name: lower case letters, digits and underscores, a letter first;
# a leading underscore passes the format and is refused as reserved.
_FIELD_FORMAT = re.compile(r"^[a-z_][a-z0-9_]*$")
# A relation table the studio names: « x_ », then lower case letters,
# digits and underscores, whatever rule the field names follow.
_TABLE_NAME = re.compile(r"^x_[a-z0-9_]+$")
_MODEL_NAME = re.compile(r"^x_[a-z][a-z0-9_]*$")
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
# The attribute that marks, in a draft arch built for the editor, the nodes
# the changes touch: space-separated « key:kind » tokens (see
# ``change_kind``); never written to a view.
CHANGE_MARK = "erplibre_studio_changes"
# The kinds of ``change_kind``, in the order the editor lists them.
CHANGE_KINDS = ("new", "renamed", "hidden", "moved", "attribute")


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


def page_refusal(node, position):
    """Why a page cannot go at ``position`` of ``node`` (an ArchError), or
    None when it can: inside a <notebook>, or before or after a <page>."""
    if (node.tag == "notebook" and position == "inside") or (
        node.tag == "page" and position in ("before", "after")
    ):
        return None
    return ArchError("A tab goes in a notebook.", "page_place")


def notebook_refusal(node, position):
    """Why a notebook cannot go at ``position`` of ``node`` (an ArchError),
    or None when it can: its parent is one of NOTEBOOK_PARENTS."""
    parent = node if position == "inside" else node.getparent()
    if parent is not None and parent.tag in NOTEBOOK_PARENTS:
        return None
    return ArchError("A notebook goes in a sheet or in a tab.", "notebook_place")


def move_refusal(view_type, node):
    """Why ``node`` cannot move (an ArchError), or None when it can."""
    parent = node.getparent()
    if parent is None or node.tag in ("templates",) + FIXED_TAGS or is_template(node):
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
    if node.tag in FIXED_TAGS:
        return ArchError(f"<{node.tag}> cannot be hidden.", "no_hide", tag=node.tag)
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


def _add_child(parent, child):
    """Append the element ``child`` {tag, attrs, children} to ``parent``: the
    sub-view of an added x2many field, made of SUBVIEW_TAGS only."""
    tag = (child or {}).get("tag")
    if tag not in SUBVIEW_TAGS:
        raise ArchError(f"A change cannot add <{tag}>.", "unknown_node", tag=tag)
    node = etree.SubElement(parent, tag)
    _set_attributes(node, child.get("attrs"))
    for item in child.get("children") or []:
        _add_child(node, item)
    return node


def _add_node(parent, node_def):
    """Append the element ``node_def`` {tag, attrs, children} of an
    « add_node » change to ``parent``: a tag of NODE_TAGS, its children of
    NODE_CHILDREN, one level deep."""
    tag = node_def.get("tag")
    if tag not in NODE_TAGS:
        raise ArchError(f"A change cannot add <{tag}>.", "unknown_node", tag=tag)
    node = etree.SubElement(parent, tag)
    _set_attributes(node, node_def.get("attrs"))
    for child in node_def.get("children") or []:
        child_tag = (child or {}).get("tag")
        if child_tag not in NODE_CHILDREN.get(tag, ()):
            raise ArchError(
                f"A change cannot add <{child_tag}>.", "unknown_node", tag=child_tag
            )
        _set_attributes(etree.SubElement(node, child_tag), child.get("attrs"))
    return node


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
            _add_node(spec, payload.get("node") or {})
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
            for child in payload.get("node_children") or []:
                _add_child(node, child)
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


def change_kind(change):
    """What ``change`` (a dict of ``change_spec``) does to its node, one of
    CHANGE_KINDS: « new » when it adds the node, « moved », « hidden »
    (hidden, or removed from a view type that hides by removing),
    « renamed » when it sets the label, else « attribute »."""
    ctype = change["type"]
    payload = change.get("payload") or {}
    if ctype in ADD_CHANGES or ctype == "add_node":
        return "new"
    if ctype == "move":
        return "moved"
    if ctype == "remove" or (ctype == "hide" and payload.get("value")):
        return "hidden"
    if ctype == "relabel" or (
        ctype == "set_attribute" and payload.get("attribute") == "string"
    ):
        return "renamed"
    return "attribute"


def _add_change_mark(node, key, kind):
    tokens = (node.get(CHANGE_MARK) or "").split()
    token = f"{key}:{kind}"
    if token not in tokens:
        node.set(CHANGE_MARK, " ".join(tokens + [token]))


def change_marks(node):
    """[(key, kind)] of the CHANGE_MARK of ``node``; the keys as text."""
    return [
        tuple(token.rsplit(":", 1)) for token in (node.get(CHANGE_MARK) or "").split()
    ]


def strip_change_marks(arch):
    """Remove the CHANGE_MARK of every node of ``arch``, in place."""
    for node in arch.xpath(f"//*[@{CHANGE_MARK}]"):
        del node.attrib[CHANGE_MARK]
    return arch


def _apply_tracked(arch, change, view_type):
    """``arch`` with ``change`` applied, a new element, the node it touches
    marked with CHANGE_MARK: the nodes its spec inserts for an added node
    (not the field a timeline item loads beside), else the node at its
    XPath (the source of a move) as it stands before the change."""
    spec = change_spec(change, view_type)
    candidate = copy.deepcopy(arch)
    kind = change_kind(change)
    key = change["key"]
    if kind == "new":
        main = spec[0] if spec.tag == "data" else spec
        for child in elements(main):
            if child.tag != "xpath":
                _add_change_mark(child, key, kind)
    else:
        payload = change.get("payload") or {}
        target = payload.get("source") if kind == "moved" else change.get("xpath")
        try:
            _add_change_mark(locate(candidate, target), key, kind)
        except ArchError:
            # The spec does not apply either, and says why.
            pass
    return apply_inheritance_specs(candidate, spec)


def apply_changes(arch, changes, view_type, message=str, mark=False, track=False):
    """Apply ``changes`` (dicts with a ``key``) in order to a copy of
    ``arch``. Return (arch, errors): a change that does not apply is
    skipped and ``errors`` maps its key to the reason, the text that
    ``message`` gives for the exception. ``mark``: the nodes a change adds
    carry ADDED_MARK, its key. ``track``: each node a change adds, moves,
    hides or sets an attribute of carries CHANGE_MARK (``_apply_tracked``);
    a node a change removes leaves the arch with its marks."""
    arch = copy.deepcopy(arch)
    errors = {}
    for change in changes:
        try:
            if track:
                arch = _apply_tracked(arch, change, view_type)
            else:
                arch = _apply_one(arch, change, view_type, mark)
        except Exception as exc:  # noqa: BLE001 - every spec error is reported
            errors[change["key"]] = message(exc)
    return arch, errors


def change_paths(arch):
    """{key: XPath} of the first node of ``arch``, in document order, that
    carries the CHANGE_MARK of each change; the keys as text."""
    paths = {}
    for node in arch.xpath(f"//*[@{CHANGE_MARK}]"):
        for key, _kind in change_marks(node):
            paths.setdefault(key, node_xpath(arch, node))
    return paths


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


def changes_on_added(arch, changes, view_type, key, child=None):
    """The keys of the changes after the change ``key`` that locate a node
    it added, or a node inside one: by their XPath or the source of a move,
    in the arch as it stands when each applies. ``child``: the name of a
    node the change adds under its top node (the page of a notebook); only
    the changes on that node, or on a node inside it, count."""
    current = copy.deepcopy(arch)
    mark = str(key) if child is None else f"{key}/{child}"
    found, after = [], False
    for change in changes:
        if after:
            paths = (change.get("xpath"), (change.get("payload") or {}).get("source"))
            if any(path and _added_by(current, path, mark) for path in paths):
                found.append(change["key"])
        if change["key"] == key:
            after = True
        try:
            current = _apply_one(current, change, view_type, mark=True)
        except Exception:  # noqa: BLE001,S112 - a change that fails is skipped
            continue
        if change["key"] == key and child is not None:
            for top in current.xpath(f"//*[@{ADDED_MARK}=$key]", key=str(key)):
                for node in top.iterdescendants():
                    if node.get("name") == child:
                        node.set(ADDED_MARK, mark)
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


# A color rule as ``colors_text`` writes it: « field operator literal ».
_COLOR_RULE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*(==|!=|>=|<=|>|<)\s*(.+)$", re.S)


def colors_rules(text):
    """[{color, expression}] of a ``colors`` attribute. A rule that
    ``colors_text`` could have written also gives its ``field``,
    ``operator`` and ``value``, so that it can be written again; another
    expression stays text only."""
    rules = []
    for part in (text or "").split(";"):
        color, sep, expression = part.partition(":")
        if sep and color.strip():
            rule = {"color": color.strip(), "expression": expression.strip()}
            rule.update(_color_rule_parts(rule["expression"]))
            rules.append(rule)
    return rules


def _color_rule_parts(expression):
    """{field, operator, value} of a color rule « field operator literal »,
    or {} when ``expression`` is not one."""
    match = _COLOR_RULE.match(expression)
    if not match:
        return {}
    try:
        value = ast.literal_eval(match.group(3).strip())
    except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
        return {}
    if not isinstance(value, (str, int, float, bool)):
        return {}
    return {"field": match.group(1), "operator": match.group(2), "value": value}


_ORDER_TERM = re.compile(r"^\s*([a-z_][a-z0-9_]*)(\s+(asc|desc))?\s*$", re.I)


def order_terms(text):
    """[(field name, « asc » or « desc »)] of an order text (« name asc,
    id desc »), a term without direction ascending; ArchError when it is
    not one."""
    terms = []
    for term in (text or "").split(","):
        match = _ORDER_TERM.match(term)
        if not match:
            raise ArchError(f"Invalid order {text}.", "bad_order", order=text)
        terms.append((match.group(1), (match.group(3) or "asc").lower()))
    return terms


def order_fields(text):
    """The field names of an order text (« name asc, id desc »); ArchError
    when it is not one."""
    return [name for name, _direction in order_terms(text)]


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
    if view_type == "form" and node.tag == "separator":
        return "separator"
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
    descend into an x2many.

    Of a draft arch built with ``apply_changes(track=True)``, a block
    gives the ``changes`` (keys, an int when the key is one) that touch
    its node and their ``change_kinds`` (CHANGE_KINDS order), ``changed``
    when there is one, and ``changed_inside`` when a block under it is
    ``changed``."""

    def walk(node, depth):
        keys = []
        kinds = set()
        for key, kind in change_marks(node):
            key = int(key) if key.isdigit() else key
            kinds.add(kind)
            if key not in keys:
                keys.append(key)
        block = {
            "path": node_xpath(root, node),
            "tag": node.tag,
            "label": node_label(node, fields, view_type),
            "attrs": _shown_attrs(node, view_type),
            "movable": depth > 0 and move_refusal(view_type, node) is None,
            "changes": keys,
            "change_kinds": [kind for kind in CHANGE_KINDS if kind in kinds],
            "changed": bool(keys),
            "changed_inside": False,
        }
        if _is_container(node, view_type, depth):
            block["kind"] = "template" if is_template(node) else "container"
            block["drop"] = _drop_container(view_type, node)
            block["children"] = [walk(child, depth + 1) for child in elements(node)]
            block["changed_inside"] = any(
                child["changed"] or child["changed_inside"]
                for child in block["children"]
            )
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


def _slug(label):
    """``label`` in ASCII lower case letters, digits and underscores."""
    text = unicodedata.normalize("NFKD", label or "").encode("ascii", "ignore")
    return re.sub(r"[^a-z0-9]+", "_", text.decode().lower()).strip("_")


def slug(label, default="item"):
    """``label`` in ASCII lower case letters, digits and underscores, at
    most 40 characters; ``default`` when nothing is left."""
    return _slug(label)[:40].rstrip("_") or default


def _free_name(base, taken):
    name, count = base, 2
    while name in taken:
        name = f"{base}_{count}"
        count += 1
    return name


def field_name_from_label(label, taken):
    """A free ``x_`` field name made of ``label``: ASCII, lower case,
    underscores, at most 63 characters, not in ``taken``."""
    base = f"x_{_slug(label) or 'field'}"[:58].rstrip("_")
    return _free_name(base, taken)


def model_name_from_label(label, taken):
    """A free ``x_`` model name made of ``label`` as
    ``field_name_from_label`` makes a field name: a letter after « x_ »,
    at most ``MODEL_NAME_SIZE`` characters, not in ``taken``."""
    slug = _slug(label) or "model"
    if not slug[0].isalpha():
        slug = f"model_{slug}"
    base = f"x_{slug}"[: MODEL_NAME_SIZE - 4].rstrip("_")
    return _free_name(base, taken)


def valid_model_name(name):
    return bool(name and len(name) <= MODEL_NAME_SIZE and _MODEL_NAME.match(name))


def default_model_arch(
    view_type,
    label,
    chatter=False,
    archivable=False,
    manual_order=False,
    per_company=False,
):
    """The arch text of the default ``view_type`` view (``MODEL_VIEW_TYPES``)
    of a model the studio creates, labelled ``label``. The form has a title
    on ``x_name`` and two empty columns to drop fields into, then the
    chatter when ``chatter``. ``archivable`` (``x_active``) adds the
    « Archived » ribbon and the field to the form and the « Archived »
    filter to the search view; ``manual_order`` puts the handle of
    ``x_sequence`` first in the list; ``per_company`` adds ``x_company_id``
    at the end of the right column of the form and after ``x_name`` in the
    list, for the multi-company users only. The arch depends on these values
    only: the changes of the editor on the view stay in an inherited view,
    so that writing the arch again never moves the nodes they locate. The
    options add nodes whose tag or name keeps the paths of the other
    nodes: a ribbon is the only <widget> of the sheet, its fields and its
    filter are located by name."""
    root = etree.Element(view_type, {"string": label})
    if view_type == "form":
        sheet = etree.SubElement(root, "sheet")
        if archivable:
            etree.SubElement(
                sheet,
                "widget",
                {
                    "name": "web_ribbon",
                    "title": "Archived",
                    "bg_color": "text-bg-danger",
                    "invisible": "x_active",
                },
            )
        title = etree.SubElement(sheet, "div", {"class": "oe_title"})
        heading = etree.SubElement(title, "h1")
        etree.SubElement(heading, "field", {"name": "x_name", "placeholder": label})
        main = etree.SubElement(sheet, "group", {"name": "studio_main"})
        etree.SubElement(main, "group", {"name": "studio_left"})
        right = etree.SubElement(main, "group", {"name": "studio_right"})
        if per_company:
            etree.SubElement(
                right,
                "field",
                {"name": "x_company_id", "groups": "base.group_multi_company"},
            )
        if archivable:
            etree.SubElement(sheet, "field", {"name": "x_active", "invisible": "1"})
        if chatter:
            etree.SubElement(root, "chatter")
    elif view_type in ("list", "search"):
        if view_type == "list" and manual_order:
            etree.SubElement(root, "field", {"name": "x_sequence", "widget": "handle"})
        etree.SubElement(root, "field", {"name": "x_name"})
        if view_type == "list" and per_company:
            etree.SubElement(
                root,
                "field",
                {
                    "name": "x_company_id",
                    "groups": "base.group_multi_company",
                    "optional": "show",
                },
            )
        if view_type == "search" and archivable:
            etree.SubElement(
                root,
                "filter",
                {
                    "name": "inactive",
                    "string": "Archived",
                    "domain": "[('x_active', '=', False)]",
                },
            )
    else:
        raise ArchError(
            f"Unknown view type {view_type}.", "unknown_view_type", type=view_type
        )
    return etree.tostring(root, encoding="unicode", pretty_print=True)


def default_view_arch(view_type, label, name_field, date_field=None, group_field=None):
    """The arch text of the ``view_type`` view (``VIEW_TYPES``) a project
    adds to an existing model, labelled ``label``: the record name
    ``name_field`` in a form, a list, a search view and a kanban card; an
    empty pivot (it counts the records); a timeline that starts on
    ``date_field``, one row per value of the many2one ``group_field``, its
    items showing the record name. The arch depends on these values only:
    the changes of the editor on the view locate their nodes in it."""
    root = etree.Element(view_type, {"string": label})
    if view_type == "form":
        sheet = etree.SubElement(root, "sheet")
        main = etree.SubElement(sheet, "group", {"name": "studio_main"})
        left = etree.SubElement(main, "group", {"name": "studio_left"})
        etree.SubElement(left, "field", {"name": name_field})
        etree.SubElement(main, "group", {"name": "studio_right"})
    elif view_type in ("list", "search"):
        etree.SubElement(root, "field", {"name": name_field})
    elif view_type == "kanban":
        templates = etree.SubElement(root, "templates")
        card = etree.SubElement(templates, "t", {"t-name": "card"})
        etree.SubElement(card, "field", {"name": name_field, "class": "fw-bold"})
    elif view_type == "timeline":
        if not date_field or not group_field:
            raise ArchError(
                "A timeline needs a date field and a many2one to group by.",
                "timeline_fields",
            )
        root.set("date_start", date_field)
        root.set("default_group_by", group_field)
        etree.SubElement(root, "field", {"name": name_field})
        templates = etree.SubElement(root, "templates")
        item = etree.SubElement(templates, "t", {"t-name": "timeline-item"})
        body = etree.SubElement(item, "div")
        etree.SubElement(body, "span", {"t-esc": f"record.{name_field}"})
    elif view_type != "pivot":
        raise ArchError(
            f"Unknown view type {view_type}.", "unknown_view_type", type=view_type
        )
    return etree.tostring(root, encoding="unicode", pretty_print=True)


def x2many_refusal(view_type, ttype):
    """Why a new field of type ``ttype`` cannot be added to a ``view_type``
    view (an ArchError), or None when it can."""
    if ttype in X2MANY_TYPES and view_type not in X2MANY_VIEW_TYPES[ttype]:
        if ttype == "one2many":
            return ArchError("A one2many shows in a form only.", "x2many_view")
        return ArchError(
            "A many2many shows in a form, a list or a kanban only.",
            "many2many_view",
        )
    return None


def x2many_node(view_type, ttype, display_field):
    """(node attributes, children) of a new x2many field in a
    ``view_type`` view: in a form, an inline sub-list of the field
    ``display_field`` of the comodel, editable for a one2many; in a list or
    a kanban, a many2many shows as tags. An inline sub-list loads no view of
    the comodel."""
    if view_type != "form":
        return {"widget": "many2many_tags"}, []
    attrs = {"editable": "bottom"} if ttype == "one2many" else {}
    sub_list = {
        "tag": "list",
        "attrs": attrs,
        "children": [{"tag": "field", "attrs": {"name": display_field}}],
    }
    return {}, [sub_list]


def many2many_names(module_name, model, comodel, field_name, taken):
    """(table, column1, column2) of a new many2many ``field_name`` of
    ``model`` to ``comodel``: the table « x_<module>_<model>_<field>_rel »,
    the model without « x_ » and the field without « x_ », or, when it
    leaves no room for a « _2 » suffix under TABLE_NAME_SIZE,
    « x_<module>_<digest>_rel »; a « _2 »... suffix keeps it out of
    ``taken``. The columns are « <table of the model>_id » and
    « <table of the comodel>_id », « id1 » and « id2 » for a relation of a
    model to itself."""
    short_model = model[2:] if model.startswith("x_") else model
    short_field = field_name[2:] if field_name.startswith("x_") else field_name
    table = f"x_{module_name}_{_slug(short_model)}_{_slug(short_field)}_rel"
    if len(table) > TABLE_NAME_SIZE - 4:
        digest = hashlib.sha1(f"{model}.{field_name}".encode()).hexdigest()[:10]
        table = f"x_{module_name[:24]}_{digest}_rel"
    base = table[: -len("_rel")]
    count = 2
    while table in taken:
        table = f"{base}_{count}_rel"
        count += 1
    if model == comodel:
        return table, "id1", "id2"
    return (
        table,
        f"{model.replace('.', '_')}_id",
        f"{comodel.replace('.', '_')}_id",
    )


def field_name_checks(name, prefix_required=True, reserved=()):
    """{format, reserved, prefix}: whether ``name`` passes each check of
    ``field_name_refusal``, each one run on its own."""
    text = name if isinstance(name, str) else ""
    return {
        "format": bool(
            text and len(text) <= FIELD_NAME_SIZE and _FIELD_FORMAT.match(text)
        ),
        "reserved": not (
            keyword.iskeyword(text)
            or text.startswith(RESERVED_FIELD_PREFIXES)
            or text in reserved
        ),
        "prefix": not prefix_required or (text.startswith("x_") and text != "x_"),
    }


def field_name_refusal(name, prefix_required=True, reserved=()):
    """Why ``name`` cannot be the name of a new field (an ArchError), or
    None when it can. The codes, in the order they are checked:
    « format » (lower case letters, digits and underscores, at most
    FIELD_NAME_SIZE characters), « reserved » (a Python keyword, a prefix of
    RESERVED_FIELD_PREFIXES, or a name of ``reserved``, the methods and
    attributes of the model), « prefix » (``prefix_required`` and no
    « x_ » followed by at least one character)."""
    checks = field_name_checks(name, prefix_required, reserved)
    messages = {
        "format": f"Invalid field name {name}: lower case letters, digits and _.",
        "reserved": f"Reserved name of the ORM {name}.",
        "prefix": f"The field name {name} needs the prefix x_.",
    }
    for code, message in messages.items():
        if not checks[code]:
            return ArchError(message, code, name=name)
    return None


def valid_field_name(name, prefix_required=True):
    return field_name_refusal(name, prefix_required) is None


def valid_table_name(name):
    """Whether ``name`` can be the relation table of a new many2many:
    « x_ », lower case letters, digits and underscores, at most
    TABLE_NAME_SIZE characters."""
    return bool(
        isinstance(name, str)
        and len(name) <= TABLE_NAME_SIZE
        and _TABLE_NAME.match(name)
    )


def valid_column_name(name):
    """Whether ``name`` can be a column of a relation table: lower case
    letters, digits and underscores, starting with a letter."""
    return bool(isinstance(name, str) and len(name) <= 63 and _MODULE_NAME.match(name))


def valid_module_name(name):
    return bool(name and len(name) <= 64 and _MODULE_NAME.match(name))
