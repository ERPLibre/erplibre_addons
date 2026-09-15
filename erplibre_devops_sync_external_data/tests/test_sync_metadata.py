# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestSyncExternalMetadata(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.module = cls.env["devops.cg.module"].create(
            {"name": "test_sync_meta"}
        )

    def _make_model(self, vals=None, fields_vals=None):
        defaults = {
            "name": "test.sync.entry",
            "module_id": self.module.id,
            "enable_sync_external": True,
        }
        if vals:
            defaults.update(vals)
        model = self.env["devops.cg.model"].create(defaults)
        for field_vals in fields_vals or []:
            self.env["devops.cg.field"].create(
                dict(field_vals, model_id=model.id)
            )
        return model

    def test_csv_metadata_basic(self):
        model = self._make_model(
            {"sync_external_file_type": "csv"},
            [
                {
                    "name": "project_code",
                    "type": "char",
                    "sync_external_associate_header_name": "Code projet",
                    "sync_external_is_primary": True,
                },
                {
                    "name": "client_name",
                    "type": "char",
                    "sync_external_associate_header_name": "Nom client",
                },
            ],
        )
        meta = model.build_sync_external_metadata()
        self.assertEqual(meta["filetype"], "csv")
        self.assertEqual(meta["index_line_header"], 0)
        self.assertEqual(meta["nb_line_header"], 1)
        self.assertEqual(meta["sync"], ["project_code"])
        self.assertIn(["Code projet", "project_code"], meta["header"])
        self.assertIn(["Nom client", "client_name"], meta["header"])
        self.assertEqual(meta["bind"], [])
        self.assertNotIn("sheet_name", meta)

    def test_xlsx_metadata_sheet_and_index(self):
        model = self._make_model(
            {
                "sync_external_file_type": "xlsx",
                "sync_external_sheet_name": "Données",
            },
            [
                {
                    "name": "z_cle",
                    "type": "char",
                    "sync_external_is_primary": True,
                }
            ],
        )
        meta = model.build_sync_external_metadata()
        self.assertEqual(meta["filetype"], "xlsx")
        self.assertEqual(meta["index_line_header"], 1)
        self.assertEqual(meta["sheet_name"], "Données")

    def test_value_map_third_header_element(self):
        model = self._make_model(
            {"sync_external_file_type": "csv"},
            [
                {
                    "name": "is_public",
                    "type": "boolean",
                    "sync_external_associate_header_name": "Info publique",
                    "sync_external_value_map": '{"oui": true, "non": false}',
                }
            ],
        )
        meta = model.build_sync_external_metadata()
        entry = next(h for h in meta["header"] if h[1] == "is_public")
        self.assertEqual(entry[0], "Info publique")
        self.assertEqual(entry[2], {"oui": True, "non": False})

    def test_ignore_data_parsed_as_list(self):
        model = self._make_model(
            {
                "sync_external_file_type": "csv",
                "sync_external_ignore_data": "FAUX\n#N/D\n  \n#VALEUR!",
            },
            [
                {
                    "name": "a",
                    "type": "char",
                    "sync_external_is_primary": True,
                }
            ],
        )
        meta = model.build_sync_external_metadata()
        self.assertEqual(meta["ignore_data"], ["FAUX", "#N/D", "#VALEUR!"])

    def test_sync_fallback_first_field_when_no_primary(self):
        model = self._make_model(
            {"sync_external_file_type": "csv"},
            [
                {"name": "first", "type": "char"},
                {"name": "second", "type": "char"},
            ],
        )
        meta = model.build_sync_external_metadata()
        self.assertEqual(meta["sync"], ["first"])

    def test_file_no_line_excluded_from_header(self):
        model = self._make_model(
            {"sync_external_file_type": "csv"},
            [
                {
                    "name": "code",
                    "type": "char",
                    "sync_external_is_primary": True,
                },
                {"name": "file_no_line", "type": "integer"},
            ],
        )
        meta = model.build_sync_external_metadata()
        names = [h[1] for h in meta["header"]]
        self.assertIn("code", names)
        self.assertNotIn("file_no_line", names)

    def test_bind_empty_when_no_bindings(self):
        model = self._make_model(
            {"sync_external_file_type": "csv"},
            [
                {
                    "name": "a",
                    "type": "char",
                    "sync_external_is_primary": True,
                }
            ],
        )
        self.assertEqual(model.build_sync_external_metadata()["bind"], [])

    def test_bind_declarative_full(self):
        model = self._make_model(
            {"sync_external_file_type": "csv"},
            [
                {
                    "name": "numero_projet",
                    "type": "char",
                    "sync_external_is_primary": True,
                },
                {"name": "titre_projet", "type": "char"},
            ],
        )
        mirror_field = self.env["devops.cg.field"].search(
            [("model_id", "=", model.id), ("name", "=", "numero_projet")],
            limit=1,
        )
        self.env["devops.cg.sync.bind"].create(
            {
                "model_id": model.id,
                "target_model": "project.project",
                "bind_field_reverse": "project_id",
                "rec_name_mode": "format",
                "rec_name_format": "%s %s",
                "rec_name_vars": "numero_projet, titre_projet",
                "binding_ids": [
                    (
                        0,
                        0,
                        {
                            "field_name": "fci_project_number",
                            "mirror_field_id": mirror_field.id,
                        },
                    )
                ],
                "default_ids": [
                    (
                        0,
                        0,
                        {
                            "key": "is_project_FCI",
                            "value_type": "bool",
                            "value": "true",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "key": "project_team_id",
                            "value_type": "char",
                            "value": "BPIR",
                        },
                    ),
                ],
            }
        )
        meta = model.build_sync_external_metadata()
        self.assertEqual(len(meta["bind"]), 1)
        cfg = meta["bind"][0]
        self.assertEqual(cfg["bind_field_reverse"], "project_id")
        pp = cfg["bind_field_model"]["project.project"]
        self.assertEqual(
            pp["rec_name"],
            {"string": "%s %s", "vars": ["numero_projet", "titre_projet"]},
        )
        self.assertEqual(
            pp["binding"][0],
            {
                "field_name": "fci_project_number",
                "mirror_field": "numero_projet",
            },
        )
        self.assertEqual(
            pp["default_field"],
            {"is_project_FCI": True, "project_team_id": "BPIR"},
        )

    def test_bind_method_call_with_extra_json(self):
        model = self._make_model(
            {"sync_external_file_type": "csv"},
            [
                {
                    "name": "code",
                    "type": "char",
                    "sync_external_is_primary": True,
                }
            ],
        )
        self.env["devops.cg.sync.bind"].create(
            {
                "model_id": model.id,
                "target_model": "crm.lead",
                "bind_field_reverse": "crm_lead_id",
                "method_call": "action_transform_test_entries",
                "method_extra_json": (
                    '{"order_lines": [{"product_name": "Services",'
                    ' "qty": 2, "price_unit": 100.0}]}'
                ),
            }
        )
        cfg = model.build_sync_external_metadata()["bind"][0]
        self.assertEqual(cfg["method_call"], "action_transform_test_entries")
        self.assertEqual(
            cfg["order_lines"],
            [{"product_name": "Services", "qty": 2, "price_unit": 100.0}],
        )
        self.assertNotIn("bind_field_model", cfg)

    def test_bind_target_model_other(self):
        model = self._make_model(
            {"sync_external_file_type": "csv"},
            [
                {
                    "name": "a",
                    "type": "char",
                    "sync_external_is_primary": True,
                }
            ],
        )
        self.env["devops.cg.sync.bind"].create(
            {
                "model_id": model.id,
                "target_model": "other",
                "target_model_other": "x.custom.model",
                "default_ids": [(0, 0, {"key": "foo", "value": "bar"})],
            }
        )
        cfg = model.build_sync_external_metadata()["bind"][0]
        self.assertIn("x.custom.model", cfg["bind_field_model"])
        self.assertEqual(
            cfg["bind_field_model"]["x.custom.model"]["default_field"],
            {"foo": "bar"},
        )

    def test_bind_group_by_emitted_as_list(self):
        model = self._make_model(
            {"sync_external_file_type": "csv"},
            [
                {
                    "name": "a",
                    "type": "char",
                    "sync_external_is_primary": True,
                }
            ],
        )
        self.env["devops.cg.sync.bind"].create(
            {
                "model_id": model.id,
                "target_model": "project.project",
                "bind_group_by": "numero_projet",
            }
        )
        cfg = model.build_sync_external_metadata()["bind"][0]
        self.assertEqual(cfg["bind_group_by"], ["numero_projet"])

    def test_sync_by_mirror_field_emitted_as_list(self):
        model = self._make_model(
            {"sync_external_file_type": "csv"},
            [
                {
                    "name": "a",
                    "type": "char",
                    "sync_external_is_primary": True,
                }
            ],
        )
        self.env["devops.cg.sync.bind"].create(
            {
                "model_id": model.id,
                "target_model": "project.project",
                "sync_by_mirror_field": "numero_projet, code_projet",
            }
        )
        cfg = model.build_sync_external_metadata()["bind"][0]
        self.assertEqual(
            cfg["sync_by_mirror_field"], ["numero_projet", "code_projet"]
        )

    def test_bind_target_other_requires_other_model(self):
        model = self._make_model(
            {"sync_external_file_type": "csv"},
            [
                {
                    "name": "a",
                    "type": "char",
                    "sync_external_is_primary": True,
                }
            ],
        )
        with self.assertRaises(ValidationError):
            self.env["devops.cg.sync.bind"].create(
                {"model_id": model.id, "target_model": "other"}
            )
