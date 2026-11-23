# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models
from odoo.exceptions import ValidationError

LAYER_KINDS = [
    ("raster", "Background"),
    ("vector", "Geo field"),
]
# The raster types the studio writes: OpenStreetMap needs no service URL.
RASTER_TYPES = [("osm", "OpenStreetMap")]
GEO_REPRESENTATIONS = [
    ("basic", "Basic"),
    ("colored", "Colored range"),
]
CLASSIFICATIONS = [
    ("unique", "Unique value"),
    ("interval", "Interval"),
    ("quantile", "Quantile"),
]
# {kind: model of base_geoengine Apply writes the layer to}.
LAYER_MODELS = {
    "raster": "geoengine.raster.layer",
    "vector": "geoengine.vector.layer",
}
# The values of a layer its snapshot keeps, in the order of the fields.
SNAPSHOT_KEYS = (
    "kind",
    "sequence",
    "name",
    "raster_type",
    "geo_field",
    "geo_repr",
    "attribute_field",
    "classification",
    "begin_color",
    "end_color",
    "nb_class",
    "active_on_startup",
)


class ErplibreStudioGeoLayer(models.Model):
    """A layer of a GeoEngine view a view line adds: Apply writes it as a
    geoengine.raster.layer (a background) or a geoengine.vector.layer (a
    geo field of the model drawn on it) of base_geoengine, bound to the
    view the line creates, under the external id ``_studio_xml_name``.
    The fields name the fields of the model by their name: the studio
    does not depend on base_geoengine, whose models exist only once it is
    installed."""

    _name = "erplibre.studio.geo.layer"
    _inherit = "erplibre.studio.line"
    _description = "ERPLibre studio geo layer"
    _order = "sequence, id"

    view_line_id = fields.Many2one(
        "erplibre.studio.view",
        string="View",
        required=True,
        ondelete="cascade",
        index=True,
    )
    kind = fields.Selection(LAYER_KINDS, required=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(required=True)
    raster_type = fields.Selection(RASTER_TYPES, default="osm")
    geo_field = fields.Char(help="The geo field of the model a vector layer draws.")
    geo_repr = fields.Selection(
        GEO_REPRESENTATIONS, string="Representation", default="basic"
    )
    attribute_field = fields.Char(
        help="The field whose values color a colored range, by its name."
    )
    classification = fields.Selection(CLASSIFICATIONS)
    begin_color = fields.Char()
    end_color = fields.Char()
    nb_class = fields.Integer(string="Number of classes", default=1)
    active_on_startup = fields.Boolean(help="The layer shows when the map opens.")

    _sql_constraints = [
        (
            "view_kind_sequence_uniq",
            "unique(view_line_id, kind, sequence)",
            "Two layers of a view share a kind and a sequence.",
        ),
    ]

    # ── external id ─────────────────────────────────────────────────────

    def _studio_xml_name(self):
        """The name, under the module of the project, of the external id of
        the layer Apply writes: « <model>_geo_<kind>_<sequence> », the model
        with its dots as underscores. The sequence, which the snapshot
        keeps, names it: Discard gives the layer back the same name."""
        self.ensure_one()
        model = self._underscored(self.view_line_id.model)
        return f"{model}_geo_{self.kind}_{self.sequence}"

    def _studio_layer_model(self):
        """The model of base_geoengine the layer is written to."""
        self.ensure_one()
        return LAYER_MODELS[self.kind]

    def _snapshot(self):
        return [
            {key: layer[key] or False for key in SNAPSHOT_KEYS}
            for layer in self.sorted(lambda layer: (layer.kind, layer.sequence))
        ]

    def _payload(self):
        """[{id, kind, name, geo_field, geo_repr, active_on_startup}]: the
        layers as the editor lists them."""
        return [
            {
                "id": layer.id,
                "kind": layer.kind,
                "name": layer.name,
                "geo_field": layer.geo_field or False,
                "geo_repr": layer.geo_repr or False,
                "active_on_startup": layer.active_on_startup,
            }
            for layer in self
        ]

    # ── constraints ─────────────────────────────────────────────────────

    @api.constrains("view_line_id", "kind", "geo_field", "project_id")
    def _check_studio_geo_layer(self):
        for layer in self:
            line = layer.view_line_id
            if line.view_type != "geoengine":
                raise ValidationError(
                    self.env._("A layer belongs to a GeoEngine view.")
                )
            if line.project_id != layer.project_id:
                raise ValidationError(
                    self.env._("A layer belongs to the project of its view.")
                )
            if layer.kind == "vector" and not layer.geo_field:
                raise ValidationError(
                    self.env._(
                        "The layer %(name)s draws no geo field.", name=layer.name
                    )
                )
