# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, models
from odoo.exceptions import UserError
from odoo.tools import sql

from .. import arch as studio_arch
from .erplibre_studio_project import protected_model

# The keys of the definition of an x2many that fix its relation: they never
# change once the field is in the draft.
RELATION_KEYS = (
    "relation",
    "relation_field",
    "inverse_new",
    "relation_table",
    "column1",
    "column2",
)


class ErplibreStudioProject(models.Model):
    """The relational fields of a project: one2many (to an existing inverse
    many2one, or to one the project creates on the comodel), many2many (to
    a relation table named after the module), and the many2one, with the
    one2many the project may create on its comodel."""

    _inherit = "erplibre.studio.project"

    # ── definitions ─────────────────────────────────────────────────────

    def _studio_field_definitions(self, model):
        """{name: (definition, change)} of the new fields of the project on
        ``model``: those its add_field changes add, and the inverse fields
        its one2many and many2one create on ``model`` (with the change of
        the field that creates them)."""
        self.ensure_one()
        result = {}
        for change in self._project_field_changes():
            payload = change._payload()
            definition = payload.get("field") or {}
            if change.model == model:
                result[payload.get("field_name")] = (definition, change)
            inverse = self._studio_inverse_definition(change.model, definition)
            if inverse and definition.get("relation") == model:
                result.setdefault(inverse[0], (inverse[1], change))
        return result

    def _studio_inverse_definition(self, model, definition):
        """(name, definition) of the inverse field the relational field
        ``definition`` of ``model`` creates on its comodel, or None: the
        many2one of a one2many (``inverse_new``), the one2many of a
        many2one (``inverse_o2m``). What the inverse many2one does when its
        record is deleted comes from the comodel, whatever the payload says:
        « cascade » on a model of the project, « set null » on a model of the
        database, whose records the deletion of a record of the project must
        never take with it."""
        ttype = definition.get("ttype")
        comodel = definition.get("relation")
        if ttype == "many2one":
            inverse = definition.get("inverse_o2m") or {}
            if not inverse.get("name"):
                return None
            return inverse["name"], {
                "ttype": "one2many",
                "field_description": inverse.get("field_description")
                or inverse["name"],
                "readonly": False,
                "help": "",
                "relation": model,
                "relation_field": inverse.get("relation_field"),
            }
        inverse = definition.get("inverse_new") or {}
        if ttype != "one2many" or not inverse.get("name"):
            return None
        return inverse["name"], {
            "ttype": "many2one",
            "field_description": inverse.get("field_description") or inverse["name"],
            "readonly": False,
            "help": "",
            "relation": model,
            "on_delete": (
                "cascade" if comodel in self._studio_new_models() else "set null"
            ),
        }

    def _studio_inverse_owner(self, model, name):
        """The add_field change of the project whose field creates the
        inverse field ``name`` on ``model`` (``_studio_inverse_definition``),
        or an empty recordset."""
        self.ensure_one()
        for change in self._project_field_changes():
            definition = change._payload().get("field") or {}
            inverse = self._studio_inverse_definition(change.model, definition)
            if inverse and inverse[0] == name and definition.get("relation") == model:
                return change
        return self._project_field_changes().browse()

    def _studio_all_definitions(self):
        """[(model, name, definition, change)] of every new field of the
        project, in the order Apply creates them: the scalar fields and the
        many2one (inverse many2one included), then the many2many, then the
        one2many, whose inverse must exist first."""
        self.ensure_one()
        items = []
        for change in self._project_field_changes():
            payload = change._payload()
            definition = payload.get("field") or {}
            items.append((change.model, payload.get("field_name"), definition, change))
            inverse = self._studio_inverse_definition(change.model, definition)
            if inverse:
                items.append((definition["relation"], *inverse, change))
        rank = {"many2many": 1, "one2many": 2}
        return sorted(items, key=lambda item: rank.get(item[2].get("ttype"), 0))

    # ── one2many / many2many ────────────────────────────────────────────

    def _studio_model_label(self, model):
        line = self.new_model_ids.filtered(lambda m: m.model == model)[:1]
        if line:
            return (line.name or "").strip() or model
        return self.env["ir.model"]._get(model).name or model

    def _studio_display_field(self, comodel):
        """The field an inline sub-list of ``comodel`` shows: ``x_name`` on
        a model of the project, else the stored field of its record names,
        else ``display_name``. An editable sub-list needs a field to type
        in: a comodel that requires its name cannot take a line without
        it."""
        if comodel in self._studio_new_models():
            return "x_name"
        Comodel = self.env.get(comodel)
        field = Comodel._fields.get(Comodel._rec_name) if Comodel is not None else None
        if field is not None and field.store and field.type == "char":
            return field.name
        return "display_name"

    def _studio_inverse_choices(self, model, comodel):
        """[{name, label, pending}] of the many2one fields of ``comodel`` to
        ``model``, the inverses a one2many of ``model`` to ``comodel`` can
        take: those of the registry (or of the simulated fields of a model of
        the project not created yet), and the new many2one of the project
        on ``comodel``, inverses of other one2many included."""
        self.ensure_one()
        choices = {}
        line = self._studio_pending_line(comodel)
        if line:
            infos = self._studio_simulated_fields(line)
            for name, info in infos.items():
                if info.get("type") == "many2one" and info.get("relation") == model:
                    choices[name] = {
                        "name": name,
                        "label": info.get("string") or name,
                        "pending": True,
                    }
        elif comodel in self.env:
            for name, field in self.env[comodel]._fields.items():
                if field.type == "many2one" and field.comodel_name == model:
                    choices[name] = {
                        "name": name,
                        "label": field.string or name,
                        "pending": False,
                    }
        for name, (definition, _change) in self._studio_field_definitions(
            comodel
        ).items():
            if definition.get("ttype") == "many2one" and (
                definition.get("relation") == model
            ):
                choices.setdefault(
                    name,
                    {
                        "name": name,
                        "label": definition.get("field_description") or name,
                        "pending": True,
                    },
                )
        return sorted(choices.values(), key=lambda c: c["label"].lower())

    def _studio_proposed_field_name(self, model, comodel, label=None):
        """The name a new relational field of ``model`` labelled ``label``
        (the label of ``comodel`` when none) takes: the one Apply gives it."""
        label = (label or "").strip() or self._studio_model_label(comodel)
        return studio_arch.field_name_from_label(label, self._taken_field_names(model))

    def _studio_proposed_inverse(self, model, comodel, taken=None):
        """(name, label) of the many2one a new one2many of ``model`` to
        ``comodel`` would create on ``comodel``: « x_<model label>_id », free
        on the comodel."""
        label = self._studio_model_label(model)
        taken = self._taken_field_names(comodel) | set(taken or ())
        return studio_arch.field_name_from_label(f"{label} id", taken), label

    def _clean_one2many(self, model, name, field):
        """The relation keys of a new one2many ``name`` of ``model``: its
        comodel and its inverse, a many2one of the comodel to ``model``, or
        ``inverse_new``, the many2one the project creates on the comodel
        (``field["inverse"]`` = {create: true, name, field_description})."""
        comodel = self._clean_relation(field)
        inverse = field.get("inverse") or {}
        if not (inverse.get("create") or field.get("inverse_new")):
            relation_field = field.get("relation_field")
            names = [c["name"] for c in self._studio_inverse_choices(model, comodel)]
            if relation_field not in names:
                raise UserError(
                    self.env._(
                        "%(name)s is not a many2one of %(comodel)s to %(model)s: "
                        "choose an inverse, or let the studio create one.",
                        name=relation_field,
                        comodel=comodel,
                        model=model,
                    )
                )
            return {"relation": comodel, "relation_field": relation_field}
        if protected_model(comodel):
            raise UserError(
                self.env._(
                    "The studio does not add fields to %(model)s: choose an "
                    "existing inverse.",
                    model=comodel,
                )
            )
        inverse = inverse or field.get("inverse_new") or {}
        taken = {name} if comodel == model else set()
        proposed, label = self._studio_proposed_inverse(model, comodel, taken)
        label = (inverse.get("field_description") or "").strip() or label
        self._check_field_texts(label, "")
        inverse_name = (inverse.get("name") or "").strip() or proposed
        if inverse_name != proposed and (
            inverse_name in self._taken_field_names(comodel) or inverse_name in taken
        ):
            raise UserError(
                self.env._("The field %(name)s already exists.", name=inverse_name)
            )
        if not studio_arch.valid_field_name(inverse_name):
            raise UserError(
                self.env._(
                    "%(name)s is not a valid field name: x_ then lower case "
                    "letters, digits and underscores.",
                    name=inverse_name,
                )
            )
        on_delete = "cascade" if comodel in self._studio_new_models() else "set null"
        return {
            "relation": comodel,
            "relation_field": inverse_name,
            "inverse_new": {
                "name": inverse_name,
                "field_description": label,
                "on_delete": on_delete,
            },
        }

    @api.model
    def _studio_inverse_o2m_name(self, label, taken):
        """The name the inverse one2many of a many2one labelled ``label``
        proposes: « x_<label>_ids », not in ``taken``."""
        return studio_arch.field_name_from_label(f"{label} ids", taken)

    def _clean_many2one_inverse(self, model, name, comodel, field, existing=None):
        """The ``inverse_o2m`` of the new many2one ``name`` of ``model`` to
        ``comodel``: {name, field_description, relation_field}, the one2many
        the project creates on the comodel, which lists the records of
        ``model`` that point to a record; None when ``field["inverse_o2m"]``
        is empty. Its label defaults to the label of ``model``, its name to
        one made of that label, free on the comodel. ``existing``: the
        definition the many2one had; while it has an inverse, its comodel
        does not change. Once the many2one is in the database, its inverse
        is neither added, removed nor renamed: only its label changes."""
        existing = existing or {}
        previous = existing.get("inverse_o2m") or {}
        if previous and comodel != existing.get("relation"):
            raise UserError(
                self.env._(
                    "Remove the inverse field %(inverse)s first: the comodel of "
                    "%(name)s does not change while it exists.",
                    inverse=previous.get("name"),
                    name=name,
                )
            )
        inverse = field.get("inverse_o2m") or {}
        if not isinstance(inverse, dict):
            inverse = {"create": True}
        applied = bool(existing) and self._studio_field_applied(model, name)
        if not inverse:
            if previous and applied:
                raise UserError(
                    self.env._(
                        "The inverse field of %(name)s changes only before Apply.",
                        name=name,
                    )
                )
            return None
        if protected_model(comodel):
            raise UserError(
                self.env._(
                    "The studio does not add fields to %(model)s: choose an "
                    "existing inverse.",
                    model=comodel,
                )
            )
        label = (
            (inverse.get("field_description") or "").strip()
            or previous.get("field_description")
            or self._studio_model_label(model)
        )
        self._check_field_texts(label, "")
        inverse_name = (inverse.get("name") or "").strip() or previous.get("name")
        if not inverse_name:
            taken = self._taken_field_names(comodel)
            if comodel == model:
                taken.add(name)
            inverse_name = self._studio_inverse_o2m_name(label, taken)
        if inverse_name != previous.get("name"):
            if applied:
                raise UserError(
                    self.env._(
                        "The inverse field of %(name)s changes only before Apply.",
                        name=name,
                    )
                )
            if comodel == model and inverse_name == name:
                raise UserError(
                    self.env._("The field %(name)s already exists.", name=name)
                )
            problem = self._studio_field_name_problem(
                comodel, inverse_name, own=previous.get("name") or None
            )
            if problem:
                raise UserError(problem["message"])
        return {
            "name": inverse_name,
            "field_description": label,
            "relation_field": name,
        }

    def _clean_many2many(self, model, name, field):
        """The relation keys of a new many2many ``name`` of ``model``: its
        comodel, and the relation table and columns the server names
        (``arch.many2many_names``); a client value of these is ignored."""
        self.ensure_one()
        comodel = self._clean_relation(field)
        table, column1, column2 = studio_arch.many2many_names(
            self.module_name, model, comodel, name, self._studio_relation_table_names()
        )
        return {
            "relation": comodel,
            "relation_table": table,
            "column1": column1,
            "column2": column2,
        }

    def _kept_relation(self, name, field, existing):
        """The relation keys of ``existing``, the definition of the x2many
        ``name``; UserError when ``field`` changes one of them."""
        kept = {key: existing[key] for key in RELATION_KEYS if key in existing}
        for key, value in kept.items():
            if key in field and field[key] != value:
                raise UserError(
                    self.env._(
                        "The relation of the field %(name)s cannot change.", name=name
                    )
                )
        return kept

    def _studio_relation_table_names(self):
        """The table names a new many2many cannot take: the tables of the
        database, the relation tables of the fields, and those of the
        many2many in the drafts of every project."""
        self.env.cr.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = current_schema()"
        )
        taken = {row[0] for row in self.env.cr.fetchall()}
        self.env.cr.execute(
            "SELECT relation_table FROM ir_model_fields WHERE relation_table IS NOT NULL"
        )
        taken |= {row[0] for row in self.env.cr.fetchall()}
        for change in (
            self.env["erplibre.studio.change"]
            .sudo()
            .search(
                [
                    ("change_type", "=", "add_field"),
                    ("payload", "ilike", "relation_table"),
                ]
            )
        ):
            table = (change._payload().get("field") or {}).get("relation_table")
            if table:
                taken.add(table)
        return taken

    def _studio_check_inverse_removal(self, changes):
        """Raise UserError when ``changes`` (add_field changes of the project
        that leave the draft) hold a many2one, or a one2many whose new
        inverse is a many2one, that another one2many of the project, which
        stays, takes as its inverse: that one2many would name a field that
        no longer exists."""
        self.ensure_one()
        staying = self._project_field_changes() - changes
        for change in changes.filtered(lambda c: c.change_type == "add_field"):
            definition = change._payload().get("field") or {}
            # [(model, name, inverse)]: the many2one fields the change
            # creates; ``inverse`` is set for the one of a one2many. The
            # one2many of a many2one is the inverse of no other field.
            created = []
            if definition.get("ttype") == "many2one" and change.field_name:
                created.append((change.model, change.field_name, False))
            inverse = self._studio_inverse_definition(change.model, definition)
            if inverse and inverse[1]["ttype"] == "many2one":
                created.append((definition["relation"], inverse[0], True))
            for model, name, is_inverse in created:
                other = next(
                    (
                        other
                        for other in staying
                        if self._studio_one2many_of(other, model, name)
                    ),
                    None,
                )
                if other is None:
                    continue
                if is_inverse:
                    raise UserError(
                        self.env._(
                            "The field %(field)s creates %(inverse)s, the inverse "
                            "of %(other)s: remove %(other)s first.",
                            field=change.field_name,
                            inverse=f"{model}.{name}",
                            other=f"{other.model}.{other.field_name}",
                        )
                    )
                raise UserError(
                    self.env._(
                        "The field %(field)s is the inverse of %(other)s: "
                        "remove %(other)s first.",
                        field=f"{model}.{name}",
                        other=f"{other.model}.{other.field_name}",
                    )
                )

    @api.model
    def _studio_one2many_of(self, change, model, name):
        """Whether the add_field ``change`` adds a one2many whose inverse is
        the existing many2one ``name`` of ``model``: not one it creates
        itself (« inverse_new »)."""
        definition = change._payload().get("field") or {}
        return (
            definition.get("ttype") == "one2many"
            and definition.get("relation") == model
            and definition.get("relation_field") == name
            and not definition.get("inverse_new")
        )

    def _studio_inverse_dependents(self, changes):
        """``changes`` (changes of the project that leave the draft) with the
        changes of the project that show an inverse field one of their
        fields creates on its comodel (``_studio_inverse_definition``), and
        the changes that depend on the nodes these add, until none is
        added: the inverse leaves the draft with its field."""
        self.ensure_one()
        result = changes
        todo = changes
        while todo:
            names = {}
            for change in todo.filtered(lambda c: c.change_type == "add_field"):
                definition = change._payload().get("field") or {}
                inverse = self._studio_inverse_definition(change.model, definition)
                if inverse:
                    names.setdefault(definition["relation"], set()).add(inverse[0])
            found = self._studio_changes_of_fields(names) if names else changes.browse()
            todo = found - result
            result |= found
        return result

    def _studio_check_relations(self):
        """Raise UserError when a relational field of the draft no longer
        applies: its comodel left the registry and the project, the inverse
        of a one2many is no longer a many2one to its model, the table of a
        many2many is too long or taken by another field."""
        self.ensure_one()
        new_models = self._studio_new_models()
        Fields = self.env["ir.model.fields"].sudo()
        tables = {}
        for model, name, definition, _change in self._studio_all_definitions():
            ttype = definition.get("ttype")
            relation = definition.get("relation")
            if ttype not in ("many2one", *studio_arch.X2MANY_TYPES):
                continue
            label = f"{model}.{name}"
            Comodel = self.env.get(relation) if relation else None
            if relation not in new_models and (
                Comodel is None or Comodel._transient or Comodel._abstract
            ):
                raise UserError(
                    self.env._(
                        "The comodel %(model)s of the field %(name)s does not "
                        "exist.",
                        model=relation,
                        name=label,
                    )
                )
            if ttype == "one2many" and not definition.get("inverse_new"):
                names = [
                    c["name"] for c in self._studio_inverse_choices(model, relation)
                ]
                if definition.get("relation_field") not in names:
                    raise UserError(
                        self.env._(
                            "The inverse %(inverse)s of the field %(name)s is no "
                            "longer a many2one to %(model)s.",
                            inverse=definition.get("relation_field"),
                            name=label,
                            model=model,
                        )
                    )
            if (ttype == "one2many" and definition.get("inverse_new")) or (
                ttype == "many2one" and definition.get("inverse_o2m")
            ):
                if protected_model(relation):
                    raise UserError(
                        self.env._(
                            "The studio does not add fields to %(model)s: choose "
                            "an existing inverse.",
                            model=relation,
                        )
                    )
            if ttype == "many2many":
                table = definition.get("relation_table") or ""
                columns = (definition.get("column1"), definition.get("column2"))
                own = Fields.search(
                    [
                        ("model", "=", model),
                        ("name", "=", name),
                        ("relation_table", "=", table),
                    ],
                    limit=1,
                )
                if (
                    len(table) > studio_arch.TABLE_NAME_SIZE
                    or not studio_arch.valid_table_name(table)
                    or not all(studio_arch.valid_column_name(c) for c in columns)
                    or columns[0] == columns[1]
                    # A table of the database, which the field would write
                    # into, and drop with the field.
                    or (not own and sql.table_exists(self.env.cr, table))
                ):
                    raise UserError(
                        self.env._(
                            "%(table)s is not a valid relation table for the "
                            "field %(name)s.",
                            table=table,
                            name=label,
                        )
                    )
                other = Fields.search(
                    [
                        ("relation_table", "=", table),
                        "!",
                        "&",
                        ("model", "=", model),
                        ("name", "=", name),
                    ],
                    limit=1,
                )
                if table in tables or other:
                    raise UserError(
                        self.env._(
                            "The relation table %(table)s of the field %(name)s "
                            "is used by another field.",
                            table=table,
                            name=label,
                        )
                    )
                tables[table] = label
