# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Key layouts of the home screen of a deck model, protocol 1.2.

A layout names, key by key, what the home screen of one deck model shows:
the home key of a plugin, a key of the dashboard (`tiles`) or a black key
(`empty`). It belongs to one layer, as a setting line does: a profile, a
deck model or a workstation, folded in that order up to the first layer
that locks the layout of that model. The workstation writes the layouts
Odoo sends to `keymap.json` (format 1 of the deck program); the actions,
the icons and the geometry of the models come from the catalog that the
workstations report.
"""

import hashlib
import json
import re
import unicodedata
from datetime import timedelta

from markupsafe import Markup
from psycopg2 import errors

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.tools import mute_logger

from .streamdeck_config import PLUGIN_ID_RE, PRODUCT_ID_RE, SOURCES
from .streamdeck_device import USB_GEOMETRY, usb_model_name
from .streamdeck_workstation import MANAGER_GROUP

# The actions of keymap.json format 1: the home key of a plugin, a key of
# the dashboard, a black key.
ACTION_RE = re.compile(r"plugin:%s|tiles|empty" % PLUGIN_ID_RE.pattern)
# The names of `ui/icons.py` ICONS in the deck program.
ICON_RE = re.compile(r"[a-z][a-z0-9_]{0,63}")
LABEL_MAX = 16
# keymap.json format 1 holds at most this many deck models.
LAYOUT_MODELS_MAX = 16
# Every workstation reports the same catalog items: their date moves at
# most once per step, so concurrent reports seldom update the same rows.
LAST_SEEN_STEP = timedelta(hours=1)

CATALOG_KINDS = [
    ("action", "Action"),
    ("icon", "Icon"),
    ("model", "Deck model"),
]


def layout_hash(layout):
    """SHA-256 hex of the canonical JSON of one model's layout, the form
    in which the workstation hashes each layout of its keymap.json
    (CONTRACT.md of the extension): `json.dumps` with sorted keys, no
    spaces, and every character outside ASCII escaped as `\\uXXXX`."""
    text = json.dumps(layout, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def _is_employee(env):
    return not env.su and not env.user.has_group(MANAGER_GROUP)


class StreamdeckCatalogItem(models.Model):
    """What the deck programs of the workstations offer: an action, an
    icon, or the geometry of a deck model.

    The catalog is the union of what the workstations reported: an item
    that no report names any more stays, `last_seen` telling when a
    workstation last offered it. Only the report service adds items.
    """

    _name = "streamdeck.catalog.item"
    _description = "Stream Deck catalog item"
    _order = "kind, value"
    _rec_names_search = ["value"]

    kind = fields.Selection(CATALOG_KINDS, required=True, readonly=True)
    value = fields.Char(
        required=True,
        readonly=True,
        help="As keymap.json writes it: plugin:<id>, tiles or empty for an"
        " action, the icon name, or the USB product id of a deck model.",
    )
    name = fields.Char(compute="_compute_name")
    last_seen = fields.Datetime(
        string="Last seen",
        readonly=True,
        help="When a workstation last reported this item; empty for an"
        " item the module ships.",
    )
    cols = fields.Integer(string="Columns", readonly=True)
    rows = fields.Integer(readonly=True)
    key_count = fields.Integer(string="Keys", readonly=True)

    _sql_constraints = [
        (
            "kind_value_unique",
            "UNIQUE(kind, value)",
            "The catalog holds each item once.",
        ),
    ]

    @api.depends("kind", "value")
    def _compute_name(self):
        for item in self:
            value = item.value or ""
            if item.kind == "model":
                item.name = usb_model_name(value)
            elif value == "tiles":
                item.name = _("Dashboard")
            elif value == "empty":
                item.name = _("Black key")
            elif value.startswith("plugin:"):
                item.name = _("Plugin %(id)s", id=value[len("plugin:") :])
            else:
                item.name = value

    @api.model
    def _take(self, catalog, now):
        """Add what `catalog` holds to the catalog and date it `now`.

        `catalog` has the wire shape `{"actions": [...], "icons": [...],
        "models": {product id: {"cols", "rows", "keys"}}}`, its entries
        already valid. A known item gets the new date when its own is
        older than LAST_SEEN_STEP; no item is removed. A new model takes
        its geometry from USB_GEOMETRY when listed there, else from
        `catalog`, and keeps it: the keys of a model are a constant of its
        hardware, and a report never changes the keys Odoo lays out for
        every workstation. Two reports that add the same item at once
        both succeed (`_insert`)."""
        Item = self.sudo()
        now = fields.Datetime.to_datetime(now)
        wanted = {("action", value): {} for value in catalog["actions"]}
        wanted.update({("icon", value): {} for value in catalog["icons"]})
        for product, shape in catalog["models"].items():
            cols, rows, keys = USB_GEOMETRY.get(
                product, (shape["cols"], shape["rows"], shape["keys"])
            )
            wanted[("model", product)] = {
                "cols": cols,
                "rows": rows,
                "key_count": keys,
            }
        if not wanted:
            return
        found = Item.search(
            [("value", "in", sorted({value for _k, value in wanted}))]
        )
        known = {(item.kind, item.value): item for item in found}
        missing = [
            dict(geometry, kind=kind, value=value, last_seen=now)
            for (kind, value), geometry in wanted.items()
            if (kind, value) not in known
        ]
        if missing and not self._insert(missing):
            for values in missing:
                self._insert([values])
        stale = Item.browse(
            [
                item.id
                for pair, item in known.items()
                if pair in wanted
                and (
                    not item.last_seen
                    or item.last_seen <= now - LAST_SEEN_STEP
                )
            ]
        )
        stale.write({"last_seen": now})

    def _insert(self, values):
        """Create `values` in a savepoint and return True; return False,
        nothing created, when one of them is in the catalog already, as
        a concurrent report inserts it."""
        try:
            with mute_logger("odoo.sql_db"), self.env.cr.savepoint():
                self.sudo().create(values)
        except errors.UniqueViolation:
            return False
        return True

    @api.model
    def _geometry(self, product_id):
        """`(cols, rows, keys)` of the deck model `product_id`: the
        module's table USB_GEOMETRY, else the geometry a workstation first
        reported, else None."""
        if (product_id or "") in USB_GEOMETRY:
            return USB_GEOMETRY[product_id]
        item = self.sudo().search(
            [("kind", "=", "model"), ("value", "=", product_id or "")],
            limit=1,
        )
        if item:
            return item.cols, item.rows, item.key_count
        return None


class StreamdeckKeyLayout(models.Model):
    """The home keys of one deck model in one layer.

    Exactly one parent: a profile, a deck model or a workstation. The
    layouts of a model fold as the setting lines do, profile < deck model
    < workstation, the first locked layout ending the fold
    (`streamdeck.config.schema._effective_layouts`); the lock is on the
    layout as a whole. Only a manager sets `locked` and `source`; an
    employee creates, changes and deletes the layouts of their own
    workstations for models that no layer locks.

    A layout `in_file` is the one the workstation's own keymap.json
    holds: a hand edit of a free layout, adopted by the report service.
    Odoo sends no layout for that model; its keys, if any, wait. Editing
    them, or « Create the keys », brings the layout back to Odoo.
    """

    _name = "streamdeck.key.layout"
    _description = "Stream Deck key layout"
    _order = "usb_product_id, id"

    usb_product_id = fields.Char(
        string="USB product id",
        size=4,
        required=True,
        help="Four hexadecimal digits: the deck model this layout is for.",
    )
    name = fields.Char(string="Deck model", compute="_compute_name")
    profile_id = fields.Many2one(
        "streamdeck.config.profile",
        string="Profile",
        index="btree_not_null",
        ondelete="cascade",
    )
    model_id = fields.Many2one(
        "streamdeck.config.model",
        string="Deck model layer",
        index="btree_not_null",
        ondelete="cascade",
    )
    workstation_id = fields.Many2one(
        "streamdeck.workstation",
        string="Workstation",
        index="btree_not_null",
        ondelete="cascade",
    )
    locked = fields.Boolean(
        help="Locked by the manager: no later layer and no employee"
        " changes the layout of this deck model.",
    )
    source = fields.Selection(
        SOURCES,
        required=True,
        default=lambda self: (
            "employee" if _is_employee(self.env) else "manager"
        ),
        help="Who set the layout: the manager, the employee, or the"
        " workstation's own file, adopted by Odoo.",
    )
    in_file = fields.Boolean(
        string="Kept in the workstation's file",
        readonly=True,
        copy=False,
        help="The workstation's keymap.json holds a layout edited by hand,"
        " which Odoo adopted: Odoo sends no layout for this deck model."
        " Create or change a key to send this one again.",
    )
    file_hash = fields.Char(
        string="Hash in the workstation's file",
        readonly=True,
        copy=False,
    )
    key_ids = fields.One2many(
        "streamdeck.key.layout.key", "layout_id", string="Keys"
    )
    cols = fields.Integer(string="Columns", compute="_compute_geometry")
    rows = fields.Integer(compute="_compute_geometry")
    key_count = fields.Integer(
        string="Number of keys", compute="_compute_geometry"
    )
    preview_html = fields.Html(
        string="Preview", compute="_compute_preview_html", sanitize=False
    )
    missing_plugins = fields.Char(
        string="Plugins without a key",
        compute="_compute_preview_html",
        help="Plugins of the catalog that have a home key and that this"
        " layout does not name: they get no key on the home screen.",
    )

    _sql_constraints = [
        (
            "profile_product_unique",
            "UNIQUE(profile_id, usb_product_id)",
            "A profile lays out each deck model once.",
        ),
        (
            "model_product_unique",
            "UNIQUE(model_id, usb_product_id)",
            "A deck model layer has one layout.",
        ),
        (
            "workstation_product_unique",
            "UNIQUE(workstation_id, usb_product_id)",
            "A workstation lays out each deck model once.",
        ),
    ]

    @api.depends("usb_product_id")
    def _compute_name(self):
        for layout in self:
            layout.name = usb_model_name(layout.usb_product_id)

    @api.depends("name", "profile_id", "model_id", "workstation_id")
    def _compute_display_name(self):
        for layout in self:
            parent = layout.profile_id or layout.workstation_id
            layout.display_name = (
                "%s — %s" % (layout.name, parent.display_name)
                if parent
                else layout.name
            )

    @api.depends("usb_product_id")
    def _compute_geometry(self):
        for layout in self:
            cols, rows, keys = layout._geometry() or (0, 0, 0)
            layout.cols, layout.rows, layout.key_count = cols, rows, keys

    @api.depends(
        "usb_product_id",
        "in_file",
        "key_ids.key_index",
        "key_ids.action_id",
        "key_ids.icon_id",
        "key_ids.label",
    )
    def _compute_preview_html(self):
        for layout in self:
            missing = layout._missing_plugins()
            layout.missing_plugins = ", ".join(missing) or False
            layout.preview_html = layout._preview(missing)

    def _missing_plugins(self):
        """The ids of the plugins of the catalog, a home key each, that
        this layout does not name; none for a layout kept in the
        workstation's file."""
        self.ensure_one()
        if self.in_file:
            return []
        plugins = (
            self.env["streamdeck.catalog.item"]
            .sudo()
            .search([("kind", "=", "action"), ("value", "=like", "plugin:%")])
            .mapped("value")
        )
        named = set(self.key_ids.mapped("action_id.value"))
        return [
            value[len("plugin:") :] for value in plugins if value not in named
        ]

    def _geometry(self):
        self.ensure_one()
        return self.env["streamdeck.catalog.item"]._geometry(
            self.usb_product_id
        )

    def _preview(self, missing=()):
        """The home screen as a grid of `rows` × `cols` cells: per key its
        index, its label or action, and its icon name; then the plugins
        of `missing`, which get no key."""
        self.ensure_one()
        if self.in_file:
            return Markup("<p>%s</p>") % _(
                "The workstation's keymap.json holds this layout, edited on"
                " the workstation: Odoo sends no layout for this deck model."
            )
        geometry = self._geometry()
        if not geometry:
            return Markup("<p>%s</p>") % _(
                "The keys of this deck model are unknown until a"
                " workstation reports its catalog."
            )
        cols, rows, count = geometry
        keys = {key.key_index: key for key in self.key_ids}
        lines = []
        for row in range(rows):
            cells = []
            for col in range(cols):
                index = row * cols + col
                if index >= count:
                    cells.append(Markup("<td></td>"))
                    continue
                key = keys.get(index)
                text, icon = "—", ""
                if key and key.action_id:
                    text = key.label or key.action_id.name
                    icon = key.icon_id.value or ""
                cells.append(
                    Markup(
                        '<td class="border text-center p-1">'
                        '<small class="text-muted">%s</small><br/>%s'
                        '<br/><small class="text-muted">%s</small></td>'
                    )
                    % (index, text, icon)
                )
            lines.append(Markup("<tr>%s</tr>") % Markup().join(cells))
        html = Markup(
            '<table class="table table-sm table-bordered mb-1">'
            "<tbody>%s</tbody></table>"
        ) % Markup().join(lines)
        if missing:
            html += Markup(
                '<div class="alert alert-warning mb-0" role="alert">'
                "%s: %s</div>"
            ) % (_("Plugins without a key"), ", ".join(missing))
        return html

    def _wire(self, plugins_off=(), catalog=None):
        """The layout as keymap.json format 1 holds it: `{"keys": [...]}`
        by ascending index, `icon` and `label` only when set. A key with
        no action is not named, and a key beyond the model's keys is left
        out. The home key of a plugin of `plugins_off` goes as a black
        key: the workstation refuses a layout that names a plugin turned
        off, and the deck program leaves its key empty.

        `catalog`, the workstation's own (`_parse_catalog` of its report),
        bounds the layout by what its deck program lays out, since the
        workstation refuses the whole revision for any key outside it: its
        number of keys of the model counts, an action it lacks goes as a
        black key as the deck program would show it, an icon it lacks is
        left out."""
        self.ensure_one()
        count = (self._geometry() or (0, 0, 0))[2]
        actions = icons = None
        if catalog is not None:
            shape = catalog["models"].get(self.usb_product_id)
            count = shape["keys"] if shape else 0
            actions, icons = set(catalog["actions"]), set(catalog["icons"])
        off = {"plugin:%s" % plugin for plugin in plugins_off}
        keys = []
        for key in self.key_ids.sorted("key_index"):
            if not key.action_id or not 0 <= key.key_index < count:
                continue
            action = key.action_id.value
            if action in off or (
                actions is not None and action not in actions
            ):
                if actions is None or "empty" in actions:
                    keys.append({"key": key.key_index, "action": "empty"})
                continue
            entry = {"key": key.key_index, "action": action}
            if key.icon_id and (icons is None or key.icon_id.value in icons):
                entry["icon"] = key.icon_id.value
            if key.label:
                entry["label"] = key.label
            keys.append(entry)
        return {"keys": keys}

    # -- constraints -----------------------------------------------------

    @api.constrains(
        "usb_product_id", "profile_id", "model_id", "workstation_id"
    )
    def _check_parent(self):
        for layout in self:
            parents = (
                layout.profile_id,
                layout.model_id,
                layout.workstation_id,
            )
            if sum(1 for parent in parents if parent) != 1:
                raise ValidationError(
                    _(
                        "A key layout belongs to exactly one profile, deck"
                        " model or workstation."
                    )
                )
            if not PRODUCT_ID_RE.fullmatch(layout.usb_product_id or ""):
                raise ValidationError(
                    _("A USB product id is four hexadecimal digits.")
                )
            if layout.model_id and (
                layout.model_id.usb_product_id != layout.usb_product_id
            ):
                raise ValidationError(
                    _(
                        "The layout of a deck model layer is for the USB"
                        " product id of that model."
                    )
                )

    @api.constrains("usb_product_id")
    def _check_keys_fit(self):
        for layout in self:
            layout.key_ids._check_index()

    # -- writes ----------------------------------------------------------

    @api.model
    def _normalized(self, vals):
        if isinstance(vals.get("usb_product_id"), str):
            vals["usb_product_id"] = vals["usb_product_id"].lower()
        if vals.get("model_id") and not vals.get("usb_product_id"):
            model = self.env["streamdeck.config.model"].sudo()
            vals["usb_product_id"] = model.browse(
                vals["model_id"]
            ).usb_product_id
        return vals

    def _check_employee_vals(self, vals):
        """Raise AccessError when an employee's `vals` sets a lock, a
        source other than theirs, the state kept by the service, or a
        parent other than one of their own workstations."""
        if (
            vals.get("locked")
            or vals.get("source", "employee") != "employee"
            or vals.get("in_file")
            or vals.get("file_hash")
            or vals.get("profile_id")
            or vals.get("model_id")
        ):
            raise AccessError(
                _(
                    "Only a Stream Deck manager sets locks, profiles and"
                    " deck models."
                )
            )
        if "workstation_id" in vals:
            workstation = self.env["streamdeck.workstation"].browse(
                vals["workstation_id"]
            )
            if not workstation:
                raise AccessError(
                    _("An employee lays out the keys of a workstation.")
                )
            workstation.check_access("write")

    @api.model
    def _check_free(self, workstation, product_id):
        """Raise AccessError when the profile of `workstation` or the
        deck model layer locks the layout of `product_id`."""
        workstation = workstation.sudo()
        domain = [
            ("usb_product_id", "=", product_id or ""),
            ("locked", "=", True),
        ]
        profile = workstation.config_profile_id
        if profile.active:
            domain += [
                "|",
                ("model_id", "!=", False),
                ("profile_id", "=", profile.id),
            ]
        else:
            domain.append(("model_id", "!=", False))
        if self.sudo().search_count(domain, limit=1):
            raise self._locked_error()

    def _locked_error(self):
        return AccessError(
            _(
                "The Stream Deck manager locked the key layout of this deck"
                " model."
            )
        )

    def _check_editable(self):
        """Raise AccessError unless an employee may change these layouts:
        layouts of their workstations, unlocked, for a model no other
        layer locks."""
        for layout in self.sudo():
            if layout.locked or not layout.workstation_id:
                raise self._locked_error()
            self._check_free(layout.workstation_id, layout.usb_product_id)

    def _touched(self):
        """Record that a person changed the keys of these layouts: the
        source becomes theirs, and a layout kept in the workstation's file
        is Odoo's again."""
        source = "employee" if _is_employee(self.env) else "manager"
        for layout in self.sudo().exists():
            values = {}
            if layout.source != source:
                values["source"] = source
            if layout.in_file:
                values.update(in_file=False, file_hash=False)
            if values:
                layout.write(values)

    @api.model_create_multi
    def create(self, vals_list):
        employee = _is_employee(self.env)
        Workstation = self.env["streamdeck.workstation"]
        vals_list = [self._normalized(dict(vals)) for vals in vals_list]
        for vals in vals_list:
            if employee:
                vals.setdefault("workstation_id", False)
                self._check_employee_vals(vals)
                self._check_free(
                    Workstation.browse(vals["workstation_id"]),
                    vals.get("usb_product_id"),
                )
        return super().create(vals_list)

    def write(self, vals):
        vals = self._normalized(dict(vals))
        if _is_employee(self.env):
            self.check_access("write")
            self._check_employee_vals(vals)
            self._check_editable()
            Workstation = self.env["streamdeck.workstation"]
            for layout in self:
                workstation = (
                    Workstation.browse(vals["workstation_id"])
                    if "workstation_id" in vals
                    else layout.workstation_id
                )
                self._check_free(
                    workstation,
                    vals.get("usb_product_id", layout.usb_product_id),
                )
        return super().write(vals)

    def unlink(self):
        if _is_employee(self.env):
            self.check_access("unlink")
            self._check_editable()
        return super().unlink()

    def action_create_keys(self):
        """Add an empty line for each key of the deck model that the
        layout lacks; the layout is Odoo's again if it was kept in the
        workstation's file."""
        Key = self.env["streamdeck.key.layout.key"]
        for layout in self:
            if _is_employee(self.env):
                layout.check_access("write")
                layout._check_editable()
            geometry = layout._geometry()
            if not geometry:
                raise ValidationError(
                    _(
                        "The keys of the deck model %(model)s are unknown"
                        " until a workstation reports its catalog.",
                        model=layout.usb_product_id,
                    )
                )
            present = set(layout.key_ids.mapped("key_index"))
            missing = [i for i in range(geometry[2]) if i not in present]
            if missing:
                Key.create(
                    [{"layout_id": layout.id, "key_index": i} for i in missing]
                )
            layout._touched()
        return True


class StreamdeckKeyLayoutKey(models.Model):
    """One key of a layout: its index, numbered row by row from the top
    left key, and what it shows. A key without action is left to the deck
    program, which places the fixtures and the dashboard there."""

    _name = "streamdeck.key.layout.key"
    _description = "Stream Deck key of a layout"
    _order = "layout_id, key_index"

    layout_id = fields.Many2one(
        "streamdeck.key.layout",
        string="Key layout",
        required=True,
        index=True,
        ondelete="cascade",
    )
    key_index = fields.Integer(
        string="Key",
        required=True,
        help="0 is the top left key; the keys are numbered row by row.",
    )
    action_id = fields.Many2one(
        "streamdeck.catalog.item",
        string="Action",
        domain=[("kind", "=", "action")],
        ondelete="restrict",
        help="The home key of a plugin, a key of the dashboard, or a black"
        " key; empty, the deck program uses the key as it sees fit.",
    )
    icon_id = fields.Many2one(
        "streamdeck.catalog.item",
        string="Icon",
        domain=[("kind", "=", "icon")],
        ondelete="restrict",
        help="Replaces the icon of the plugin's home key.",
    )
    label = fields.Char(
        help="At most 16 characters; replaces the text of the plugin's"
        " home key.",
    )

    _sql_constraints = [
        (
            "layout_index_unique",
            "UNIQUE(layout_id, key_index)",
            "A layout names each key once.",
        ),
    ]

    @api.constrains("key_index", "layout_id")
    def _check_index(self):
        for key in self:
            count = (key.layout_id._geometry() or (0, 0, 0))[2]
            if not 0 <= key.key_index < count:
                raise ValidationError(
                    _(
                        "Key %(index)s is not a key of the deck model"
                        " %(model)s.",
                        index=key.key_index,
                        model=key.layout_id.name,
                    )
                )

    @api.constrains("action_id", "icon_id", "label", "layout_id")
    def _check_values(self):
        for key in self:
            if key.action_id and key.action_id.kind != "action":
                raise ValidationError(_("The action of a key is an action."))
            if key.icon_id and key.icon_id.kind != "icon":
                raise ValidationError(_("The icon of a key is an icon."))
            label = key.label or ""
            if len(label) > LABEL_MAX or any(
                unicodedata.category(char) in ("Cc", "Cs") for char in label
            ):
                raise ValidationError(
                    _(
                        "A key label holds at most 16 characters and no"
                        " control character."
                    )
                )
            action = key.action_id.value or ""
            if action.startswith("plugin:") and self.sudo().search_count(
                [
                    ("layout_id", "=", key.layout_id.id),
                    ("action_id", "=", key.action_id.id),
                    ("id", "!=", key.id),
                ],
                limit=1,
            ):
                raise ValidationError(
                    _("A plugin has one home key in a layout.")
                )

    def _check_layouts(self, layouts):
        """For an employee, raise AccessError unless they may change the
        keys of `layouts`."""
        if _is_employee(self.env):
            layouts.check_access("write")
            layouts._check_editable()

    @api.model_create_multi
    def create(self, vals_list):
        layouts = self.env["streamdeck.key.layout"].browse(
            {
                vals.get("layout_id")
                for vals in vals_list
                if vals.get("layout_id")
            }
        )
        self._check_layouts(layouts)
        keys = super().create(vals_list)
        keys.layout_id._touched()
        return keys

    def write(self, vals):
        layouts = self.layout_id
        if vals.get("layout_id"):
            layouts |= layouts.browse(vals["layout_id"])
        if _is_employee(self.env):
            self.check_access("write")
        self._check_layouts(layouts)
        result = super().write(vals)
        layouts._touched()
        return result

    def unlink(self):
        layouts = self.layout_id
        if _is_employee(self.env):
            self.check_access("unlink")
        self._check_layouts(layouts)
        result = super().unlink()
        layouts._touched()
        return result


class StreamdeckConfigSchema(models.AbstractModel):
    _inherit = "streamdeck.config.schema"

    def _effective_layouts(self, workstation):
        """The layout of each deck model connected to `workstation`.

        Returns `{product id: {"layout": layout, "source": layer,
        "locked": bool}}` for the connected models that a layer lays out,
        by ascending product id. The layout of a model is that of the last
        layer that has one, up to the first layer whose layout is locked:
        the profile's, the deck model layer's, then the workstation's. A
        model no layer lays out is absent: the deck program places its
        keys itself.
        """
        workstation = workstation.sudo()
        products = self._connected_products(workstation)
        if not products:
            return {}
        layers = []
        profile = workstation.config_profile_id
        if profile.active:
            layers.append(("profile", profile.layout_ids))
        deck_models = (
            self.env["streamdeck.config.model"]
            .sudo()
            .search([("usb_product_id", "in", products)])
        )
        layers.append(("model", deck_models.layout_ids))
        layers.append(("workstation", workstation.layout_ids))
        result = {}
        for product in products:
            for layer, layouts in layers:
                layout = layouts.filtered(
                    lambda item, pid=product: item.usb_product_id == pid
                )[:1]
                if not layout:
                    continue
                result[product] = {
                    "layout": layout,
                    "source": layer,
                    "locked": layout.locked,
                }
                if layout.locked:
                    break
        return result

    def _layout_settings(self, layouts, plugins_off=(), catalog=None):
        """`{product id: layout}` that Odoo sends, from
        `_effective_layouts`, within `catalog`, the workstation's own
        catalog (`_wire`): neither a layout kept in the workstation's file
        nor one of a model that `catalog` does not describe, at most
        LAYOUT_MODELS_MAX models, the lowest product ids first; the home
        keys of `plugins_off` go black. None without `catalog`: the
        workstation refuses every layout when its deck program gives no
        catalog, and with them the settings of the revision."""
        sent = {}
        if catalog is None:
            return sent
        for product, entry in layouts.items():
            layout = entry["layout"]
            if layout.in_file or product not in catalog["models"]:
                continue
            if len(sent) == LAYOUT_MODELS_MAX:
                break
            sent[product] = layout._wire(plugins_off, catalog)
        return sent

    def _layout_hash(self, layout):
        return layout_hash(layout)
