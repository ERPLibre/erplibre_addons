import json
import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class DevopsOperateLocalai(models.Model):
    _name = "devops.operate.localai"
    _inherit = ["mail.activity.mixin", "mail.thread"]
    _description = "devops_operate_localai"

    name = fields.Char(tracking=True)

    last_result = fields.Text(
        readonly=True,
        tracking=True,
    )

    last_result_message = fields.Text(
        readonly=True,
        tracking=True,
    )

    last_result_url = fields.Char(
        readonly=True,
        tracking=True,
    )

    instance_exec_id = fields.Many2one(
        comodel_name="devops.instance.exec",
        string="Instance Exec",
        tracking=True,
    )

    request_url = fields.Char(
        required=True,
        tracking=True,
    )

    prompt = fields.Text(tracking=True)

    prompt_compute = fields.Text(
        tracking=True,
        compute="_compute_prompt_compute",
        store=True,
    )

    feature = fields.Selection(
        selection=[
            ("generate_text", "Generate text"),
            ("generate_image", "Generate image"),
        ],
        required=True,
        tracking=True,
        default="generate_text",
    )

    model_name_llm = fields.Selection(
        selection=[("mistral-openorca", "Mistral OpenOrca")],
        required=True,
        tracking=True,
        default="mistral-openorca",
    )

    step = fields.Integer(
        tracking=True,
        default=10,
    )

    temperature = fields.Float(default=0.1, tracking=True)

    system_id = fields.Many2one(
        comodel_name="devops.system",
        string="System",
        required=True,
        tracking=True,
    )

    gen_img_detail_level_id = fields.Many2one(
        comodel_name="devops.gen.img.detail",
        string="Detail level",
        tracking=True,
    )

    gen_img_light_ids = fields.Many2many(
        comodel_name="devops.gen.img.light",
        string="Light",
        tracking=True,
    )

    gen_img_style_artist_ids = fields.Many2many(
        comodel_name="devops.gen.img.style_artist",
        string="Style artist",
        tracking=True,
    )

    gen_img_style_type_ids = fields.Many2many(
        comodel_name="devops.gen.img.style_type",
        string="Style type",
        tracking=True,
    )

    gen_img_texture_ids = fields.Many2many(
        comodel_name="devops.gen.img.texture",
        string="Texture",
        tracking=True,
    )

    gen_img_size = fields.Selection(
        selection=[
            # ("256x256", "256x256"),
            ("512x512", "512x512"),
            # ("1024x1024", "1024x1024"),
        ],
        required=True,
        tracking=True,
        default="512x512",
    )

    cmd = fields.Char(
        compute="_compute_cmd", store=True, tracking=True
    )

    def execute_ia(self):
        for rec in self:
            cmd = rec.cmd
            out, status = rec.system_id.execute_with_result(
                cmd, None, return_status=True
            )
            if status == 0:
                json_out = out[: out.rfind("}") + 1]
                data = json.loads(json_out)
                has_error = data.get("error")
                if has_error:
                    _logger.error(data)
                    continue
                if rec.feature == "generate_image":
                    rec.last_result_url = data.get("data")[0].get("url")
                    rec.last_result = json_out
                    rec.last_result_message = False
                elif rec.feature == "generate_text":
                    rec.last_result_url = False
                    rec.last_result_message = (
                        data.get("choices")[0].get("message").get("content")
                    ).strip()
                    rec.last_result = json_out
                else:
                    _logger.error(f"Feature not supported '{rec.feature}'")
            else:
                _logger.error(out)

    @api.depends(
        "gen_img_detail_level_id",
        "gen_img_light_ids",
        "gen_img_style_artist_ids",
        "gen_img_style_type_ids",
        "gen_img_texture_ids",
        "prompt",
    )
    def _compute_prompt_compute(self):
        for rec in self:
            prompt = rec.prompt
            if rec.gen_img_detail_level_id:
                str_detail_level = rec.gen_img_detail_level_id.name
                prompt += f" – image {str_detail_level}"
            if rec.gen_img_light_ids:
                str_light = " et ".join(
                    [a.name for a in rec.gen_img_light_ids]
                )
                prompt += f" – style d'éclairage de type {str_light}"
            if rec.gen_img_style_artist_ids:
                str_style_artist = " et de ".join(
                    [a.name for a in rec.gen_img_style_artist_ids]
                )
                prompt += f" – style de {str_style_artist}"
            if rec.gen_img_style_type_ids:
                str_style_type = " et ".join(
                    [a.name for a in rec.gen_img_style_type_ids]
                )
                prompt += f" – style {str_style_type}"
            if rec.gen_img_texture_ids:
                str_texture = " et ".join(
                    [a.name for a in rec.gen_img_texture_ids]
                )
                prompt += f" – texture {str_texture}"
            rec.prompt_compute = prompt

    @api.depends(
        "request_url",
        "feature",
        "step",
        "temperature",
        "model_name_llm",
        "gen_img_size",
        "prompt_compute",
    )
    def _compute_cmd(self):
        for rec in self:
            # TODO The char ' causes a bug into the prompt
            # /bin/sh: 1: Syntax error: Unterminated quoted string
            if rec.prompt_compute:
                # prompt = rec.prompt_compute.replace("'", "").replace("{", "\\{").replace("}", "\\}").replace("\n", "")
                prompt = rec.prompt_compute.replace("'", "").replace("\n", "")
            else:
                prompt = ""
            if rec.feature == "generate_image":
                rec.cmd = f"curl {rec.request_url}/v1/images/generations"
                rec.cmd += ' -H "Content-Type:application/json"'
                rec.cmd += (
                    ' -d "{ \\"prompt\\": \\"%s\\", \\"step\\": %s,'
                    ' \\"size\\": \\"%s\\" }"'
                    % (prompt, rec.step, rec.gen_img_size)
                )
            elif rec.feature == "generate_text":
                rec.cmd = f"curl {rec.request_url}/v1/chat/completions"
                rec.cmd += ' -H "Content-Type:application/json"'
                rec.cmd += (
                    ' -d "{ \\"model\\": \\"%s\\", \\"messages\\":'
                    ' [{\\"content\\": \\"%s\\", \\"temperature\\": %s,'
                    ' \\"role\\": \\"user\\"}] }"'
                    % (rec.model_name_llm, prompt, rec.temperature)
                )
            else:
                rec.cmd = False
