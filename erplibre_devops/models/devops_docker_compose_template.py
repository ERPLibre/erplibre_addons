# !/usr/bin/env python3
# © 2021-2025 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import _, api, fields, models


class DevopsDockerComposeTemplate(models.Model):
    _name = "devops.docker.compose.template"
    _description = "devops_docker_compose_template"
    _rec_name = "name_info"

    name = fields.Char()

    name_info = fields.Char(compute="_compute_name_info", store=True)

    active = fields.Boolean(default=True)

    docker_compose_model = fields.Selection(
        selection=[
            ("erplibre", "ERPLibre"),
            ("rocketchat", "RocketChat"),
            ("nextcloud", "Nextcloud"),
            ("localai", "LocalAI"),
        ],
        required=True,
        default="erplibre",
        help="Instance list, from project list.",
    )

    is_support_gpu = fields.Boolean(
        default=False, help="If true, show gpu_mode", readonly=True
    )

    with_mistra_openorca = fields.Boolean(
        default=False,
        help=(
            "If true, force to use mistra openorca for generate text in french"
        ),
    )

    gpu_mode = fields.Selection(
        selection=[
            ("no_gpu", "No GPU"),
            ("gpu_cuda_11", "GPU Cuda 11"),
            ("gpu_cuda_12", "GPU Cuda 12"),
        ],
        required=True,
        default="no_gpu",
        help="Choose a GPU mode.",
    )

    port_1 = fields.Integer(
        default=8080,
        readonly=False,
        help="Principal port",
    )

    port_2 = fields.Integer(help="Second port")

    port_3 = fields.Integer(help="Third port")

    type_ids = fields.Many2many(
        comodel_name="devops.instance.type",
        string="Types",
    )

    is_generic_template = fields.Boolean()

    yaml = fields.Text(
        compute="_compute_yaml",
        store=True,
    )

    @api.depends(
        "name",
        "docker_compose_model",
        "is_support_gpu",
        "gpu_mode",
        "port_1",
        "type_ids",
    )
    def _compute_name_info(self):
        for rec in self:
            rec.name_info = f"{rec.name} {rec.docker_compose_model} {[a.name for a in rec.type_ids]} {rec.port_1}"
            if rec.is_support_gpu:
                rec.name += f" {rec.gpu_mode}"

    @api.depends("docker_compose_model", "gpu_mode", "port_1")
    def _compute_yaml(self):
        for rec in self:
            if rec.docker_compose_model == "erplibre":
                rec.yaml = "fds"
            elif rec.docker_compose_model == "rocketchat":
                rec.yaml = "fds"
            elif rec.docker_compose_model == "nextcloud":
                rec.yaml = "fds"
            elif rec.docker_compose_model == "localai":
                if rec.gpu_mode == "gpu_cuda_11":
                    image = "localai/localai:latest-aio-gpu-nvidia-cuda-11"
                elif rec.gpu_mode == "gpu_cuda_12":
                    image = "localai/localai:latest-aio-gpu-nvidia-cuda-12"
                else:
                    if rec.with_mistra_openorca:
                        image = "localai/localai:v2.12.4-ffmpeg-core"
                    else:
                        image = "localai/localai:latest-aio-cpu"

                deploy = ""
                if rec.gpu_mode in ["gpu_cuda_11", "gpu_cuda_12"]:
                    deploy = """
    deploy:
     resources:
       reservations:
         devices:
           - driver: nvidia
             count: 1
             capabilities: [gpu]""".strip()

                command = ""
                if rec.gpu_mode in ["no_gpu"] and rec.with_mistra_openorca:
                    command = f"command: mistral-openorca"

                rec.yaml = f"""
version: "3.9"
services:
  api:
    image: {image}
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/readyz"]
      interval: 1m
      timeout: 20m
      retries: 5
    ports:
      - {rec.port_1}:8080
    environment:
      - DEBUG=true
    {command}
    volumes:
      - ./models:/build/models:cached
    {deploy}
""".strip()
            else:
                rec.yaml = False
