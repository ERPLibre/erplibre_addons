# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""Where the views, the fields and the methods of a model come from.

Everything is read from the registry classes of the running process and
from the source files on disk: no ORM write, no subprocess. A
``SourceCache`` keeps the files read during one call.
"""

import collections
import inspect
import os
import re

from lxml import etree
from odoo.models import is_definition_class
from odoo.tools.misc import file_path

# Field attributes that tie a field to a method or another field: an
# override that sets one of them changes the behaviour, not only a label.
BEHAVIOUR_ATTRS = ("compute", "inverse", "search", "related", "default")
# Field method attributes followed along the class hierarchy.
METHOD_ATTRS = ("compute", "inverse", "search")


class SourceCache:
    """File contents and source locations read during one call."""

    def __init__(self):
        self._lines = {}
        self._class_lines = {}

    def lines(self, path):
        """The lines of the file ``path``, or an empty list."""
        if path not in self._lines:
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    self._lines[path] = fh.read().splitlines()
            except OSError:
                self._lines[path] = []
        return self._lines[path]

    def location(self, obj):
        """(absolute file, first line) of a function or a class, or
        (False, 0) when the source is not reachable."""
        obj = getattr(obj, "__func__", obj)
        try:
            path = inspect.getsourcefile(obj)
        except TypeError:
            return False, 0
        if not path:
            return False, 0
        path = os.path.realpath(path)
        if isinstance(obj, type):
            return path, self.class_start(obj)
        code = getattr(obj, "__code__", None)
        return path, self.def_line(path, code.co_firstlineno) if code else 0

    def def_line(self, path, start):
        """The ``def`` line of a function whose first line is ``start``: the
        code object counts its decorators."""
        lines = self.lines(path)
        for number in range(start, min(start + 40, len(lines)) + 1):
            if re.match(r"^\s*(async\s+)?def\s", lines[number - 1]):
                return number
        return start

    def class_start(self, cls):
        """First line of the class statement of ``cls``: the line that
        reads ``class <name>(`` where the qualified name is unique in the
        file, else the first such line."""
        if cls in self._class_lines:
            return self._class_lines[cls]
        start = getattr(cls, "__firstlineno__", 0)
        if not start:
            try:
                path = inspect.getsourcefile(cls)
            except TypeError:
                path = None
            pattern = re.compile(rf"^\s*class\s+{re.escape(cls.__name__)}\b")
            for number, text in enumerate(self.lines(path) if path else [], 1):
                if pattern.match(text):
                    start = number
                    break
        self._class_lines[cls] = start
        return start

    def field_line(self, cls, name):
        """Line of ``name = fields.…`` in the body of ``cls``; the class
        line when the assignment is not found."""
        path, start = self.location(cls)
        if not path:
            return False, 0
        pattern = re.compile(rf"^\s+{re.escape(name)}\s*=\s*fields\.")
        lines = self.lines(path)
        for number in range(max(start, 1), len(lines) + 1):
            if pattern.match(lines[number - 1]):
                return path, number
            if number > start and re.match(r"^class\s", lines[number - 1]):
                break
        return path, start


def definition_classes(model):
    """The definition classes behind ``model``, base first: one per Python
    class that defines or extends the model, its mixins included."""
    return [
        cls
        for cls in reversed(type(model).__mro__)
        if is_definition_class(cls) and cls.__dict__.get("_module") is not None
    ]


def core_classes(model):
    """The classes of the Odoo core (``odoo.models``) behind ``model``."""
    return [
        cls
        for cls in reversed(type(model).__mro__)
        if is_definition_class(cls)
        and not cls.__dict__.get("_module")
        and cls.__module__.startswith("odoo.")
        and not cls.__module__.startswith("odoo.addons.")
    ]


def _origin(cls, path=None, line=0, **extra):
    module = cls.__dict__.get("_module") or False
    entry = {
        "module": module,
        "core": not module,
        "class_name": cls.__qualname__,
        "file": path or False,
        "line": line or 0,
    }
    entry.update(extra)
    return entry


def method_origins(model, name, cache):
    """The definitions of the method ``name`` along the classes of
    ``model``, base first; each with its module, file and line."""
    result = []
    for cls in core_classes(model) + definition_classes(model):
        func = cls.__dict__.get(name)
        if func is None or not callable(getattr(func, "__func__", func)):
            continue
        path, line = cache.location(func)
        result.append(_origin(cls, path, line, method=name))
    return result


def decorated_methods(model, attr):
    """{field name: [method name, …]} of the methods that carry the
    decorator attribute ``attr`` (``_onchange``, ``_constrains``) in a
    class of ``model``. A field named in a dotted path counts by its
    first part."""
    found = collections.defaultdict(list)
    for cls in core_classes(model) + definition_classes(model):
        for method_name, func in cls.__dict__.items():
            names = getattr(func, attr, None)
            if not names or callable(names) or isinstance(names, str):
                continue
            for field_name in names:
                key = str(field_name).split(".")[0]
                if method_name not in found[key]:
                    found[key].append(method_name)
    return found


def field_origins(model, name, cache, onchanges=None, constrains=None):
    """Where the field ``name`` of ``model`` comes from.

    Return a dict: ``definitions`` lists each class that declares the
    field, base first, with the attributes it passes; ``defined_in`` is
    the first one; ``overrides`` lists, after the first declaration,
    every later declaration and every class that defines one of its
    methods (compute, inverse, search), its onchange methods and its
    constraints. A field that ``_inherits`` delegates names the model
    it comes from in ``inherited_model``.
    """
    field = model._fields[name]
    onchanges = (
        onchanges if onchanges is not None else decorated_methods(model, "_onchange")
    )
    constrains = (
        constrains
        if constrains is not None
        else decorated_methods(model, "_constrains")
    )
    definitions = []
    for cls in core_classes(model) + definition_classes(model):
        declared = cls.__dict__.get(name)
        if declared is None or not hasattr(declared, "_args__"):
            continue
        path, line = cache.field_line(cls, name)
        args = sorted(k for k in (declared._args__ or {}) if not k.startswith("_"))
        definitions.append(_origin(cls, path, line, kind="field", attrs=args))
    overrides = [
        dict(entry, behaviour=any(a in BEHAVIOUR_ATTRS for a in entry["attrs"]))
        for entry in definitions[1:]
    ]
    for attr in METHOD_ATTRS:
        method = getattr(field, attr, None)
        method_name = (
            method if isinstance(method, str) else getattr(method, "__name__", None)
        )
        if not method_name:
            continue
        for entry in method_origins(model, method_name, cache):
            overrides.append(dict(entry, kind=attr, behaviour=True))
    for kind, mapping in (("onchange", onchanges), ("constrains", constrains)):
        for method_name in mapping.get(name, ()):
            for entry in method_origins(model, method_name, cache):
                overrides.append(dict(entry, kind=kind, behaviour=True))
    inherited_model = False
    if getattr(field, "inherited", False) and field.related_field is not None:
        inherited_model = field.related_field.model_name
    compute = field.compute
    defined_in = definitions[0] if definitions else False
    override_modules = sorted(
        {
            o["module"]
            for o in overrides
            if o["module"] and o["module"] != (defined_in or {}).get("module")
        }
    )
    return {
        "name": name,
        "string": field.string,
        "type": field.type,
        "relation": getattr(field, "comodel_name", None) or False,
        "store": bool(field.store),
        "readonly": bool(field.readonly),
        "required": bool(field.required),
        "compute": (
            compute if isinstance(compute, str) else getattr(compute, "__name__", False)
        )
        or False,
        "related": field.related or False,
        "inherited_model": inherited_model,
        "manual": field.manual,
        "modules": sorted(m for m in (field._modules or ()) if m),
        "definitions": definitions,
        "defined_in": defined_in,
        "overrides": overrides,
        "override_modules": override_modules,
    }


# ── views ──────────────────────────────────────────────────────────────


def view_location(view, cache):
    """(absolute file, line) of the record of ``view`` in its XML file,
    from ``arch_fs`` and the external id; (False, 0) for a view without
    file."""
    if not view.arch_fs:
        return False, 0
    try:
        path = os.path.realpath(file_path(view.arch_fs))
    except (FileNotFoundError, ValueError):
        return False, 0
    xml_id = view.xml_id or ""
    if "." not in xml_id:
        return path, 0
    module, name = xml_id.split(".", 1)
    pattern = re.compile(
        rf"""\bid\s*=\s*["'](?:{re.escape(module)}\.)?{re.escape(name)}["']"""
    )
    for number, text in enumerate(cache.lines(path), 1):
        if pattern.search(text):
            return path, number
    return path, 0


def _parse(arch):
    try:
        return etree.fromstring((arch or "<data/>").encode())
    except etree.XMLSyntaxError:
        return None


def _locator(node):
    """The XPath an inheritance spec targets: ``expr`` of an ``xpath``
    node, else the tag and its attributes, ``position`` aside."""
    if node.tag == "xpath":
        return node.get("expr") or ""
    attrs = "".join(
        f"[@{key}='{value}']"
        for key, value in node.attrib.items()
        if key not in ("position", "position_after")
    )
    return f"//{node.tag}{attrs}"


def view_specs(arch):
    """The inheritance specs of an extension arch: a list of
    {expr, position, attributes}, and the field names the view adds or
    targets. A ``<data>`` root holds the specs; any other root is one."""
    root = _parse(arch)
    if root is None:
        return [], []
    nodes = list(root) if root.tag == "data" else [root]
    specs = []
    fields_seen = []

    def add_field(name):
        if name and name not in fields_seen:
            fields_seen.append(name)

    for node in nodes:
        if not isinstance(node.tag, str):
            continue
        position = node.get("position", "inside")
        attributes = [
            a.get("name") for a in node if getattr(a, "tag", None) == "attribute"
        ]
        specs.append(
            {
                "expr": _locator(node),
                "position": position,
                "attributes": [a for a in attributes if a],
            }
        )
        if node.tag == "field":
            add_field(node.get("name"))
        else:
            match = re.search(
                r"field\[@name=['\"]([\w.]+)['\"]\]", node.get("expr") or ""
            )
            if match:
                add_field(match.group(1))
        for child in node.iter("field"):
            if child is not node:
                add_field(child.get("name"))
    return specs, fields_seen


def applied_views(view):
    """The views combined into ``view``'s arch, in the order Odoo applies
    them: the root of its inheritance chain, then each extension, primary
    views after the extensions of their parent (``ir.ui.view._combine``).
    """
    chain = []
    node = view
    while node:
        chain.append(node.id)
        node = node.inherit_id
    View = view.browse(chain).with_context(check_view_ids=list(chain))
    root = View.browse(chain[-1])
    tree_views = View._get_inheriting_views()
    hierarchy = collections.defaultdict(list)
    for item in tree_views:
        hierarchy[item.inherit_id].append(item)
    order = [root]
    queue = collections.deque(sorted(hierarchy[root], key=lambda v: v.mode))
    while queue:
        item = queue.popleft()
        order.append(item)
        for child in reversed(hierarchy[item]):
            if child.mode == "primary":
                queue.append(child)
            else:
                queue.appendleft(child)
    return order


def arch_fields(arch_tree):
    """The ``<field>`` nodes of the arch that belong to its own model, in
    document order, without the nodes of the sub-views of a relational
    field. Each one is {name, invisible, readonly, required, widget,
    groups}, first occurrence kept."""
    result = []
    seen = set()
    for node in arch_tree.iter("field"):
        name = node.get("name")
        if not name or name in seen:
            continue
        parent = node.getparent()
        nested = False
        while parent is not None:
            if parent.tag == "field":
                nested = True
                break
            parent = parent.getparent()
        if nested:
            continue
        seen.add(name)
        result.append(
            {
                "name": name,
                "invisible": node.get("invisible") or False,
                "readonly": node.get("readonly") or False,
                "required": node.get("required") or False,
                "widget": node.get("widget") or False,
                "groups": node.get("groups") or False,
            }
        )
    return result
