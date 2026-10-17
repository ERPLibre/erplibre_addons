# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""View architecture helpers of the studio editor.

A studio change becomes one inheritance spec applied to the combined arch
of a view. Each node shown by the editor carries an XPath that locates it
in the arch as it stands when the next change applies: the combined arch
with the earlier changes of the project already applied. Changes apply in
their sequence, so a recorded XPath keeps pointing at the same node.
"""

import copy
import re
import unicodedata

from lxml import etree
from odoo.tools.template_inheritance import apply_inheritance_specs

VIEW_TYPES = ("form", "list")
POSITIONS = ("before", "after", "inside")

# The elements the editor lays out with their children; a field dropped
# « inside » one of DROP_CONTAINERS lands at its end.
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
}
DROP_CONTAINERS = {
    "form": ("sheet", "group", "page", "div"),
    "list": ("list",),
}

# The node attributes the editor shows and edits.
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
CHANGE_TYPES = ADD_CHANGES + ("move", "hide") + tuple(ATTRIBUTE_CHANGES)

OPTIONAL_VALUES = ("", "show", "hide")

_SAFE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_FIELD_NAME = re.compile(r"^x_[a-z0-9_]+$")
_MODULE_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


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


def elements(node):
    """The element children of ``node``, without comments."""
    return [child for child in node if isinstance(child.tag, str)]


def _named_expr(node):
    name = node.get("name")
    if name and _SAFE_NAME.match(name):
        return f"//{node.tag}[@name='{name}']"
    return None


def node_xpath(root, node):
    """An XPath of ``node`` in ``root``: by name when the name finds this
    node first (the inheritance specs take the first match), else by
    position under the nearest such ancestor."""
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


def _bool_text(value):
    return "True" if value else "False"


def change_spec(change, view_type):
    """The inheritance spec (an ``xpath`` element) of ``change``, a dict
    {type, xpath, position, payload}. A new element each call: applying a
    spec moves its children into the arch."""
    ctype = change["type"]
    payload = change.get("payload") or {}
    if ctype not in CHANGE_TYPES:
        raise ArchError(f"Unknown change type {ctype}.", "unknown_change", type=ctype)
    if ctype in ADD_CHANGES or ctype == "move":
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
        else:
            node = etree.SubElement(spec, "field", name=payload["field_name"])
            for key, value in sorted((payload.get("node_attrs") or {}).items()):
                node.set(key, str(value))
        return spec
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


def apply_changes(arch, changes, view_type, message=str):
    """Apply ``changes`` (dicts with a ``key``) in order to a copy of
    ``arch``. Return (arch, errors): a change that does not apply is
    skipped and ``errors`` maps its key to the reason, the text that
    ``message`` gives for the exception."""
    arch = copy.deepcopy(arch)
    errors = {}
    for change in changes:
        try:
            spec = change_spec(change, view_type)
            candidate = apply_inheritance_specs(copy.deepcopy(arch), spec)
        except Exception as exc:  # noqa: BLE001 - every spec error is reported
            errors[change["key"]] = message(exc)
            continue
        arch = candidate
    return arch, errors


def view_arch(changes, view_type):
    """The arch of the inherited view that holds ``changes``: a <data> of
    their specs, as a string."""
    data = etree.Element("data")
    for change in changes:
        data.append(change_spec(change, view_type))
    return etree.tostring(data, encoding="unicode", pretty_print=True)


def node_label(node, fields):
    """The text the editor shows for ``node``; ``fields`` maps field names
    to their description (``fields_get``)."""
    if node.tag == "field":
        info = fields.get(node.get("name")) or {}
        return node.get("string") or info.get("string") or node.get("name")
    for attr in ("string", "name", "for"):
        if node.get(attr):
            return node.get(attr)
    text = " ".join("".join(node.itertext()).split())
    return text[:60] or node.tag


def arch_blocks(root, view_type, fields):
    """The editor tree of ``root``: nested dicts {path, tag, kind, label,
    attrs, children, drop, name}. In a form, any element with children is
    a container, so that a field inside a title shows. A field never shows
    its sub-views: the editor does not descend into an x2many."""
    containers = CONTAINERS[view_type]
    drops = DROP_CONTAINERS[view_type]

    def walk(node, depth):
        block = {
            "path": node_xpath(root, node),
            "tag": node.tag,
            "label": node_label(node, fields),
            "attrs": {k: node.get(k) for k in SHOWN_ATTRS if node.get(k) is not None},
        }
        if node.tag == "field":
            block["kind"] = "field"
            block["name"] = node.get("name")
        elif (node.tag in containers or elements(node)) and (
            view_type == "form" or depth == 0
        ):
            block["kind"] = "container"
            block["drop"] = node.tag in drops
            block["children"] = [walk(child, depth + 1) for child in elements(node)]
        else:
            block["kind"] = "other"
        return block

    return walk(root, 0)


def arch_field_names(root):
    """The names of the fields of ``root``, sub-views included."""
    return {node.get("name") for node in root.iter("field") if node.get("name")}


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
