import json
import logging
import random

from odoo import _, api, exceptions, fields, models

_logger = logging.getLogger(__name__)


class DevopsPlanProject(models.Model):
    _name = "devops.plan.project"
    _inherit = ["mail.activity.mixin", "mail.thread"]
    _description = "devops_plan_project"

    name = fields.Char(
        compute="_compute_name",
        store=True,
    )

    society_name = fields.Char(
        required=True,
        track_visibility="onchange",
        help="Society name",
    )

    temperature = fields.Float(default=0.1, track_visibility="onchange")

    step = fields.Integer(
        track_visibility="onchange",
        default=20,
    )

    has_requirement_to_install = fields.Boolean()

    gen_nb_aliment = fields.Integer(
        track_visibility="onchange",
        default=5,
    )

    type_context = fields.Char(
        track_visibility="onchange",
        help="Will generate about this type context",
    )

    website_max_number_one_pager = fields.Integer(
        track_visibility="onchange",
        default=10,
    )

    project_type = fields.Selection(
        selection=[
            (
                "website_one_pager_alimentation",
                "Website one pager en Alimentation",
            ),
            ("website_one_pager_sante", "Website one pager Santé"),
            ("website_one_pager_magasin", "Website one pager Magasin"),
            ("presentation_pptx_formation", "Presentation pptx formation"),
        ],
        required=True,
        track_visibility="onchange",
        default="website_one_pager_alimentation",
        help="Will use DevOps tools to create this project type.",
    )

    has_aliment = fields.Boolean(
        track_visibility="onchange",
        compute="_compute_has_aliment",
        store=True,
    )

    result_list_aliment_count = fields.Integer(
        track_visibility="onchange",
        compute="_compute_result_list_aliment_count",
        store=True,
        help="Will count the aliment from question question_list_aliment",
    )

    result_list_aliment_image = fields.Text(
        track_visibility="onchange",
        help="A URL link to an image per line",
    )

    question_list_aliment_image = fields.Text(
        track_visibility="onchange",
        help=(
            "The question for result_list_aliment_image, auto-generate from"
            " question_list_aliment when execute."
        ),
    )

    advance_aliment_template_repas_image = fields.Char(
        default=(
            "Gros plan d'un magnifique plat de «%s» d'une beauté extrême"
            " décrit comme «%s»"
        ),
        help=(
            "Need 2 argument, will be aliment name and aliment description max"
            " 100 char."
        ),
    )

    society_type = fields.Selection(
        selection=[
            ("projet", "Projet"),
            ("projet entrepreneurial", "Projet entrepreneurial"),
            ("société", "Société"),
            ("industrie", "Industrie"),
            ("magasin", "Magasin"),
            ("restaurant", "Restaurant"),
            ("entreprise", "Entreprise"),
            ("société à but non lucratif", "OBNL"),
        ],
        required=True,
        track_visibility="onchange",
        default="projet",
    )

    question_one_pager_introduction = fields.Text(
        track_visibility="onchange",
        compute="_compute_question",
        store=True,
    )

    question_list_aliment = fields.Text(
        track_visibility="onchange",
        compute="_compute_question",
        store=True,
    )

    result_list_aliment = fields.Text(
        track_visibility="onchange",
        help=(
            "List of aliment, by csv, separate by ;. Use header : name,"
            " description"
        ),
    )

    result_one_pager_introduction = fields.Text(track_visibility="onchange")

    question_one_pager_background_introduction = fields.Text(
        track_visibility="onchange",
        compute="_compute_question",
        store=True,
    )

    result_one_pager_background_introduction = fields.Char(
        track_visibility="onchange"
    )

    instance_exec_text_id = fields.Many2one(
        comodel_name="devops.instance.exec",
        string="Instance Exec Text",
        track_visibility="onchange",
    )

    instance_exec_image_id = fields.Many2one(
        comodel_name="devops.instance.exec",
        string="Instance Exec Image",
        track_visibility="onchange",
    )

    @api.multi
    @api.depends(
        "society_name", "project_type", "type_context", "society_type"
    )
    def _compute_name(self):
        for rec in self:
            rec.name = (
                f"{rec.society_type} {rec.society_name} - {rec.project_type} -"
                f" context {rec.type_context}"
            )

    @api.multi
    @api.depends("project_type", "society_type")
    def _compute_has_aliment(self):
        for rec in self:
            rec.has_aliment = (
                rec.project_type == "website_one_pager_alimentation"
                or rec.society_type == "restaurant"
            )

    @api.depends(
        "society_name",
        "project_type",
        "website_max_number_one_pager",
        "type_context",
    )
    def _compute_question(self):
        for rec in self:
            message = ""
            message_background = ""
            rec.question_list_aliment = ""
            if rec.project_type == "website_one_pager_alimentation":
                message = (
                    "Génère moi un texte de"
                    f" {rec.website_max_number_one_pager} mots, un"
                    f" {rec.society_type} nommé {rec.society_name} sur le"
                    " sujet d'une introduction fabrique des"
                    f" {rec.type_context}"
                )
                message_background = (
                    f"Aliments «{rec.type_context}» d'une beauté extreme sur"
                    " une table de restaurant bien décoré."
                )
                rec.question_list_aliment = (
                    f"Génère moi {rec.gen_nb_aliment} nom d'aliment de"
                    f" «{rec.type_context}» avec une description. Ta réponse"
                    " doit etre sous le format json, tel que le gabarit"
                    " suivant : {'aliment':[{'name':'Aliment"
                    " 1','description':'Description Aliment"
                    " 1'},{'name':'Aliment 2','description':'Description"
                    " Aliment 2'}]}, En remplaçant Aliment 1 par un produit"
                    f" alimentaire similaire à «{rec.type_context}», ainsi que"
                    " Aliment 2."
                )
            elif rec.project_type == "website_one_pager_sante":
                message = (
                    "Génère moi un texte de"
                    f" {rec.website_max_number_one_pager} mots, un"
                    f" {rec.society_type} nommé {rec.society_name} sur le"
                    f" sujet d'une introduction sur la {rec.type_context} dans"
                    " le contexte du domaine de la santé."
                )
                message_background = (
                    "Présentation des produits sur les soins de santé"
                    f" «{rec.type_context}» avec des spécialistes."
                )
            elif rec.project_type == "website_one_pager_magasin":
                message = (
                    "Génère moi un texte de"
                    f" {rec.website_max_number_one_pager} mots sur le projet"
                    f" {rec.society_name} pour donner une envie au"
                    " consommateur de venir acheter des produits dans un"
                    f" magasin de {rec.type_context}"
                )
                message_background = (
                    f"Présentation des produits «{rec.type_context}» dans un"
                    " superbe emballage sur des présentoirs de comptoir du"
                    " magasin."
                )
            elif rec.project_type == "presentation_pptx_formation":
                nb_page = 10
                context = (
                    "domaine de la nutrition et spécifiquement sur le produit"
                    " Cordyceps"
                )
                message = (
                    f"Donne moi une formation de {nb_page} pages, dont chaque"
                    f" page a un titre et une description, sur le {context}?"
                    " Ta réponse doit etre sous le format json, tel que le"
                    " gabarit suivant : {'formation':[{'titre':'Titre"
                    " 1','description':'Description 1'},{'titre':'Titre"
                    " 2','description':'Description 2'}]}. En remplaçant"
                    " «Titre 1» par le titre et «Description 1» par la"
                    " description."
                )
                message_background = ""
            rec.question_one_pager_introduction = message
            rec.question_one_pager_background_introduction = message_background

    @api.multi
    def clear_result(self):
        for rec in self:
            rec.result_one_pager_introduction = ""
            rec.result_one_pager_background_introduction = ""
            rec.result_list_aliment = ""
            rec.result_list_aliment_image = ""
            rec.question_list_aliment_image = ""

    @api.multi
    @api.depends("has_aliment", "result_list_aliment")
    def _compute_result_list_aliment_count(self):
        for rec in self:
            lst_aliment = []
            if rec.has_aliment and rec.result_list_aliment:
                dct_aliment_items = json.loads(rec.result_list_aliment)
                lst_aliment = dct_aliment_items.get("aliment")
            rec.result_list_aliment_count = len(lst_aliment)

    @api.multi
    def install_requirement(self):
        set_module_need = {"website"}
        module_ids = self.env["ir.module.module"].search(
            [
                ("name", "in", list(set_module_need)),
                ("state", "!=", "installed"),
            ]
        )
        if module_ids:
            for module_id in module_ids:
                module_id.button_immediate_install()
                self.has_requirement_to_install = False
                return {
                    "type": "ir.actions.client",
                    "tag": "reload",
                }

    @api.multi
    def execute(self):
        for rec in self:
            if rec.project_type == "presentation_pptx_formation":
                if rec.instance_exec_text_id:
                    if not rec.result_one_pager_introduction:
                        op_value = {
                            "prompt": rec.question_one_pager_introduction,
                            "feature": "generate_text",
                            "system_id": self.env.ref(
                                "erplibre_devops.devops_system_local"
                            ).id,
                            "request_url": rec.instance_exec_text_id.url,
                            "temperature": rec.temperature,
                        }
                        op_id = self.env["devops.operate.localai"].create(
                            op_value
                        )
                        op_id.execute_ia()
                        if op_id.last_result_message:
                            rec.result_one_pager_introduction = (
                                op_id.last_result_message.replace("\n", "")
                            )
                    result_1 = rec.result_one_pager_introduction
                    try:
                        dct_formation = json.loads(
                            rec.result_one_pager_introduction
                        )
                        lst_form = dct_formation.get("formation")
                        for dct_form in lst_form:
                            more = dct_form.get("more")
                            if more:
                                continue
                            desc = dct_form.get("description")
                            new_prompt = f"Peux-tu élaborer sur {desc}"
                            op_value = {
                                "prompt": new_prompt,
                                "feature": "generate_text",
                                "system_id": self.env.ref(
                                    "erplibre_devops.devops_system_local"
                                ).id,
                                "request_url": rec.instance_exec_text_id.url,
                                "temperature": rec.temperature,
                            }
                            op_id = self.env["devops.operate.localai"].create(
                                op_value
                            )
                            op_id.execute_ia()
                            if op_id.last_result_message:
                                dct_form["more"] = op_id.last_result_message

                        for dct_form in lst_form:
                            if not rec.instance_exec_image_id:
                                break
                            picture = dct_form.get("picture")
                            if picture:
                                continue

                            desc = dct_form.get("description")

                            prompt_img = desc
                            op_value = {
                                "prompt": prompt_img,
                                "feature": "generate_image",
                                "system_id": self.env.ref(
                                    "erplibre_devops.devops_system_local"
                                ).id,
                                "request_url": rec.instance_exec_image_id.url,
                                "step": rec.step,
                                "gen_img_detail_level_id": self.env.ref(
                                    "erplibre_devops.devops_gen_img_detail_02"
                                ).id,
                                "gen_img_light_ids": [
                                    (
                                        6,
                                        0,
                                        self.env.ref(
                                            "erplibre_devops.devops_gen_img_light_04"
                                        ).ids,
                                    )
                                ],
                            }
                            op_img_id = self.env[
                                "devops.operate.localai"
                            ].create(op_value)
                            op_img_id.execute_ia()
                            if op_img_id.last_result_url:
                                dct_form["picture"] = op_img_id.last_result_url

                        result_1 = json.dumps(dct_formation)
                    except Exception as e:
                        # TODO create an execution error
                        _logger.error(
                            "Cannot parse json from variable"
                            " result_one_pager_introduction, ignore and"
                            " continue"
                        )
                    rec.result_one_pager_introduction = result_1
                    value = {"data": result_1}
                    pptx_id = self.env["devops.plan.project.pptx"].create(
                        value
                    )
                    pptx_id.execute()
                continue

            # with rec.workspace_id.devops_create_exec_bundle(
            #     "Execute plan project"
            # ) as rec_ws:
            # if not rec.question_one_pager_introduction:
            #     raise ValueError("Need a project type.")
            # TODO il faut choisir un instance de déploiement ou en créer une, default local
            # TODO installer website,website_snippet_all
            # TODO générer du texte
            # TODO créer du contenu sur le site web
            # TODO request_url auto_fill search existing localAI
            set_module_need = {"website"}
            module_ids = self.env["ir.module.module"].search(
                [
                    ("name", "in", list(set_module_need)),
                    ("state", "!=", "installed"),
                ]
            )
            if module_ids:
                rec.has_requirement_to_install = True
                continue

            if not rec.result_one_pager_introduction:
                if rec.instance_exec_text_id:
                    op_value = {
                        "prompt": rec.question_one_pager_introduction,
                        "feature": "generate_text",
                        "system_id": self.env.ref(
                            "erplibre_devops.devops_system_local"
                        ).id,
                        "request_url": rec.instance_exec_text_id.url,
                        "temperature": rec.temperature,
                    }
                    op_id = self.env["devops.operate.localai"].create(op_value)
                    op_id.execute_ia()
                    if op_id.last_result_message:
                        rec.result_one_pager_introduction = (
                            op_id.last_result_message.replace("\n", "<br />")
                        )
                else:
                    rec.result_one_pager_introduction = rec.type_context

            if (
                rec.has_aliment
                and not rec.result_list_aliment
                and rec.question_list_aliment
                and rec.instance_exec_text_id
            ):
                op_value = {
                    "prompt": rec.question_list_aliment,
                    "feature": "generate_text",
                    "system_id": self.env.ref(
                        "erplibre_devops.devops_system_local"
                    ).id,
                    "request_url": rec.instance_exec_text_id.url,
                    "temperature": rec.temperature,
                }
                op_id = self.env["devops.operate.localai"].create(op_value)
                op_id.execute_ia()
                rec.result_list_aliment = op_id.last_result_message.replace(
                    "\n", ""
                )

            if not rec.result_one_pager_background_introduction:
                if rec.instance_exec_image_id:
                    op_value = {
                        "prompt": rec.question_one_pager_background_introduction,
                        "feature": "generate_image",
                        "system_id": self.env.ref(
                            "erplibre_devops.devops_system_local"
                        ).id,
                        "request_url": rec.instance_exec_image_id.url,
                        "step": rec.step,
                        "gen_img_detail_level_id": self.env.ref(
                            "erplibre_devops.devops_gen_img_detail_02"
                        ).id,
                        "gen_img_light_ids": [
                            (
                                6,
                                0,
                                self.env.ref(
                                    "erplibre_devops.devops_gen_img_light_04"
                                ).ids,
                            )
                        ],
                    }
                    op_img_id = self.env["devops.operate.localai"].create(
                        op_value
                    )
                    op_img_id.execute_ia()
                    rec.result_one_pager_background_introduction = (
                        op_img_id.last_result_url
                    )

            if (
                rec.has_aliment
                and not rec.result_list_aliment_image
                and rec.result_list_aliment
                and rec.result_list_aliment_count
            ):
                try:
                    dct_aliment_items = json.loads(rec.result_list_aliment)
                    lst_aliment = dct_aliment_items.get("aliment")
                    lst_image_url = []
                    if rec.question_list_aliment_image is False:
                        rec.question_list_aliment_image = ""
                    for dct_aliment in lst_aliment:
                        if not rec.question_list_aliment_image:
                            aliment_name = dct_aliment.get("name")
                            aliment_description = dct_aliment.get(
                                "description"
                            )
                            prompt = (
                                rec.advance_aliment_template_repas_image
                                % (
                                    aliment_name,
                                    aliment_description[:100],
                                )
                            )
                            rec.question_list_aliment_image += f"{prompt}\n"
                        else:
                            prompt = rec.question_list_aliment_image
                        op_value = {
                            "prompt": prompt,
                            "feature": "generate_image",
                            "system_id": self.env.ref(
                                "erplibre_devops.devops_system_local"
                            ).id,
                            "request_url": rec.instance_exec_image_id.url,
                            "step": rec.step,
                            "gen_img_detail_level_id": self.env.ref(
                                "erplibre_devops.devops_gen_img_detail_02"
                            ).id,
                            "gen_img_light_ids": [
                                (
                                    6,
                                    0,
                                    self.env.ref(
                                        "erplibre_devops.devops_gen_img_light_04"
                                    ).ids,
                                )
                            ],
                        }
                        op_img_id = self.env["devops.operate.localai"].create(
                            op_value
                        )
                        op_img_id.execute_ia()
                        lst_image_url.append(op_img_id.last_result_url)

                    rec.result_list_aliment_image = "\n".join(lst_image_url)
                except Exception as e:
                    # TODO create an execution error
                    _logger.error(
                        "Cannot parse json from variable result_list_aliment,"
                        " ignore and continue"
                    )

            if rec.result_one_pager_background_introduction:
                span_introduction_image = f"""<span class="s_parallax_bg oe_img_bg oe_custom_bg" style="background-image: url('{rec.result_one_pager_background_introduction}'); background-position: 50.00% 100.00%;"/>"""
            else:
                span_introduction_image = ""

            home_page_id = self.env["ir.ui.view"].search(
                [
                    ("key", "=", "website.homepage"),
                    ("website_id", "!=", False),
                ],
                limit=1,
            )

            extra_arch_db = ""
            if rec.project_type == "website_one_pager_alimentation":
                try:
                    dct_aliment_items = json.loads(rec.result_list_aliment)
                    lst_aliment = dct_aliment_items.get("aliment")
                    lst_url_aliment = rec.result_list_aliment_image.split("\n")
                    html_aliment = ""
                    for i, dct_aliment in enumerate(lst_aliment):
                        aliment_name = dct_aliment.get("name")
                        aliment_description = dct_aliment.get("description")
                        aliment_url = lst_url_aliment[i]
                        price = random.randint(1, 30)
                        html_aliment += f"""
  <div class="row">
    <div class="col-lg-4 text-center">
      <img src="{aliment_url}" alt="#" class="img img-fluid d-block mx-auto"/>
    </div>
    <div class="col-lg-8 s_full_menu_content_description">
      <h4 class="o_default_snippet_text">{aliment_name}<span class="slash o_default_snippet_text"><span class="price o_default_snippet_text"> | </span> {price}.00$</span></h4>
      <p class="o_default_snippet_text">{aliment_description}</p>
    </div>
  </div>
"""
                    extra_arch_db = f"""
          <section class="s_full_menu">
            <div class="container-fluid">
              <h2 class="o_default_snippet_text">Menu à la carte</h2>
              <div class="row menu-container">
                <!--<div class="col-lg-2 text-center">
                  <h4 class="o_default_snippet_text">Hamburgers</h4>
                  <i class="fa fa-glass fa-5x"/>
                </div>-->
                <div class="col-lg-10 s_full_menu_content">
                    {html_aliment}
                </div>
              </div>
            </div>
          </section>
    """
                except Exception as e:
                    _logger.error(e)

            arch_db = f"""<t name="Homepage" t-name="website.homepage1">
    <t t-call="website.layout">
    <t t-set="pageName" t-value="'homepage'"/>
    <div id="wrap" class="oe_structure oe_empty">
      <section class="s_cover parallax s_parallax_is_fixed bg-black-50 pt96 pb96 s_parallax_no_overflow_hidden" data-scroll-background-ratio="1" style="background-image: none; --darkreader-inline-bgimage: none;" data-darkreader-inline-bgimage="">
        {span_introduction_image}
        <div class="container">
          <div class="row s_nb_column_fixed">
            <div class="col-lg-12 s_title" data-name="Title">
              <h1 class="s_title_thin o_default_snippet_text" style="font-size: 62px; text-align: center;">{rec.society_name}</h1>
            </div>
            <div class="col-lg-12 s_text pt16 pb16" data-name="Text">
              <p class="lead o_default_snippet_text" style="text-align: center;">{rec.result_one_pager_introduction}</p>
            </div>
            <div class="col-lg-12 s_btn text-center pt16 pb16" data-name="Buttons">
              <a href="/aboutus" class="btn btn-delta rounded-circle o_default_snippet_text">À propos</a>
              <a href="/contactus" class="btn btn-primary rounded-circle o_default_snippet_text">Contactez-nous</a>
            </div>
          </div>
        </div>
      </section>
      {extra_arch_db}
    </div>
    </t>
</t>
            """
            home_page_id.arch_db = arch_db
