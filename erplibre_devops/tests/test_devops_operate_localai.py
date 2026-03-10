# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)

from odoo.tests.common import TransactionCase


class TestDevopsOperateLocalai(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.system = cls.env["devops.system"].search([], limit=1)
        if not cls.system:
            cls.system = cls.env["devops.system"].create(
                {"method": "local"}
            )

    def _create_localai(self, vals=None):
        defaults = {
            "name": "Test AI",
            "request_url": "http://localhost:8080",
            "system_id": self.system.id,
            "prompt": "Hello world",
        }
        if vals:
            defaults.update(vals)
        return self.env["devops.operate.localai"].create(defaults)

    # ── Defaults ──

    def test_default_feature(self):
        rec = self._create_localai()
        self.assertEqual(rec.feature, "generate_text")

    def test_default_model_name(self):
        rec = self._create_localai()
        self.assertEqual(rec.model_name_llm, "mistral-openorca")

    def test_default_temperature(self):
        rec = self._create_localai()
        self.assertAlmostEqual(rec.temperature, 0.1)

    def test_default_step(self):
        rec = self._create_localai()
        self.assertEqual(rec.step, 10)

    def test_default_img_size(self):
        rec = self._create_localai()
        self.assertEqual(rec.gen_img_size, "512x512")

    # ── Computed prompt ──

    def test_prompt_compute_basic(self):
        rec = self._create_localai({"prompt": "A cat"})
        self.assertEqual(rec.prompt_compute, "A cat")

    def test_prompt_compute_with_detail(self):
        detail = self.env["devops.gen.img.detail"].create(
            {"name": "highly detailed"}
        )
        rec = self._create_localai(
            {
                "prompt": "A cat",
                "gen_img_detail_level_id": detail.id,
            }
        )
        self.assertIn("highly detailed", rec.prompt_compute)
        self.assertIn("A cat", rec.prompt_compute)

    def test_prompt_compute_with_light(self):
        light = self.env["devops.gen.img.light"].create(
            {"name": "cinematic"}
        )
        rec = self._create_localai(
            {
                "prompt": "A sunset",
                "gen_img_light_ids": [(4, light.id)],
            }
        )
        self.assertIn("cinematic", rec.prompt_compute)

    def test_prompt_compute_with_style_artist(self):
        artist = self.env["devops.gen.img.style_artist"].create(
            {"name": "Van Gogh"}
        )
        rec = self._create_localai(
            {
                "prompt": "Flowers",
                "gen_img_style_artist_ids": [(4, artist.id)],
            }
        )
        self.assertIn("Van Gogh", rec.prompt_compute)

    def test_prompt_compute_with_style_type(self):
        style = self.env["devops.gen.img.style_type"].create(
            {"name": "watercolor"}
        )
        rec = self._create_localai(
            {
                "prompt": "Mountain",
                "gen_img_style_type_ids": [(4, style.id)],
            }
        )
        self.assertIn("watercolor", rec.prompt_compute)

    def test_prompt_compute_with_texture(self):
        texture = self.env["devops.gen.img.texture"].create(
            {"name": "rough"}
        )
        rec = self._create_localai(
            {
                "prompt": "Wall",
                "gen_img_texture_ids": [(4, texture.id)],
            }
        )
        self.assertIn("rough", rec.prompt_compute)

    def test_prompt_compute_all_options(self):
        detail = self.env["devops.gen.img.detail"].create(
            {"name": "ultra"}
        )
        light = self.env["devops.gen.img.light"].create(
            {"name": "neon"}
        )
        artist = self.env["devops.gen.img.style_artist"].create(
            {"name": "Monet"}
        )
        style = self.env["devops.gen.img.style_type"].create(
            {"name": "impressionist"}
        )
        texture = self.env["devops.gen.img.texture"].create(
            {"name": "smooth"}
        )
        rec = self._create_localai(
            {
                "prompt": "Garden",
                "gen_img_detail_level_id": detail.id,
                "gen_img_light_ids": [(4, light.id)],
                "gen_img_style_artist_ids": [(4, artist.id)],
                "gen_img_style_type_ids": [(4, style.id)],
                "gen_img_texture_ids": [(4, texture.id)],
            }
        )
        for word in ["Garden", "ultra", "neon", "Monet",
                      "impressionist", "smooth"]:
            self.assertIn(word, rec.prompt_compute)

    # ── Computed cmd ──

    def test_cmd_generate_text(self):
        rec = self._create_localai(
            {"prompt": "Test prompt", "feature": "generate_text"}
        )
        self.assertIn("/v1/chat/completions", rec.cmd)
        self.assertIn("curl", rec.cmd)
        self.assertIn("mistral-openorca", rec.cmd)

    def test_cmd_generate_image(self):
        rec = self._create_localai(
            {"prompt": "A dog", "feature": "generate_image"}
        )
        self.assertIn("/v1/images/generations", rec.cmd)
        self.assertIn("512x512", rec.cmd)

    def test_cmd_generate_sound(self):
        rec = self._create_localai(
            {"prompt": "Hello", "feature": "generate_son"}
        )
        self.assertIn("/tts", rec.cmd)
        self.assertIn("test_generate_sound.wav", rec.cmd)

    def test_cmd_strips_single_quotes(self):
        rec = self._create_localai(
            {"prompt": "It's a test", "feature": "generate_text"}
        )
        # Single quotes are removed to prevent shell issues
        self.assertNotIn("'", rec.cmd.split("curl")[1])

    def test_cmd_empty_prompt(self):
        rec = self._create_localai(
            {"prompt": False, "feature": "generate_text"}
        )
        self.assertIn("curl", rec.cmd)

    # ── filename_from_url ──

    def test_filename_from_url(self):
        rec = self._create_localai()
        name = rec._filename_from_url(
            "http://example.com/images/photo.png"
        )
        self.assertEqual(name, "photo.png")

    def test_filename_from_url_encoded(self):
        rec = self._create_localai()
        name = rec._filename_from_url(
            "http://example.com/my%20file.jpg"
        )
        self.assertEqual(name, "my file.jpg")

    def test_filename_from_url_no_path(self):
        rec = self._create_localai()
        name = rec._filename_from_url("http://example.com/")
        self.assertEqual(name, "download")
