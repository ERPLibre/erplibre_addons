import datetime
import json
import logging
import textwrap
import urllib.request
import uuid

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from pptx import Presentation
from pptx.chart.data import CategoryChartData, ChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Inches, Pt

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class DevopsPlanProjectPptx(models.Model):
    _name = "devops.plan.project.pptx"
    _description = "devops_plan_project_pptx"

    name = fields.Char()

    data = fields.Text()

    @api.multi
    def execute(self):
        cst_max_word_per_line = 100
        for rec in self:
            dct_formation = {}
            try:
                dct_formation = json.loads(rec.data)
            except Exception as e:
                # TODO create an execution error
                _logger.error(
                    "Cannot parse json from variable"
                    " result_one_pager_introduction, ignore and continue"
                )

            title = (
                "Automated Presentation Creating Process\n            How to"
                " Create PowerPoint Presentations with Python "
            )
            pylogo = "pylogo.png"
            pptlogo = "pptlogo.png"
            prs = Presentation()

            # front page
            # -----------------------------------------------------------------------------------------------------------------------
            slide = prs.slides.add_slide(prs.slide_layouts[6])
            prs.slide_width = Inches(16)
            prs.slide_height = Inches(9)

            shape = slide.shapes.add_shape(
                MSO_SHAPE.RECTANGLE,
                0,
                Inches(9 / 1.5),
                Inches(16),
                Inches(9 / 8.5),
            )
            shape.shadow.inherit = False
            fill = shape.fill
            fill.solid()
            fill.fore_color.rgb = RGBColor(255, 0, 0)
            shape.text = title
            line = shape.line
            line.color.rgb = RGBColor(255, 0, 0)
            logo1 = slide.shapes.add_picture(
                pylogo,
                Inches(13.8),
                Inches(6.0),
                height=Inches(1.0),
                width=Inches(1.0),
            )
            logo2 = slide.shapes.add_picture(
                pptlogo,
                Inches(14.5),
                Inches(5.8),
                height=Inches(1.5),
                width=Inches(1.5),
            )

            # Content pages
            lst_formation = dct_formation.get("formation")
            for dct_form in lst_formation:
                slide = prs.slides.add_slide(prs.slide_layouts[6])

                shape = slide.shapes.add_shape(
                    MSO_SHAPE.RECTANGLE,
                    0,
                    Inches(0.5),
                    Inches(16),
                    Inches(0.3),
                )
                shape.shadow.inherit = False
                fill = shape.fill
                fill.solid()
                fill.fore_color.rgb = RGBColor(255, 0, 0)
                shape.text = dct_form.get("titre")
                line = shape.line
                line.color.rgb = RGBColor(255, 0, 0)
                logo1 = slide.shapes.add_picture(
                    pylogo,
                    Inches(14.5),
                    Inches(0.4),
                    height=Inches(0.5),
                    width=Inches(0.5),
                )
                logo2 = slide.shapes.add_picture(
                    pptlogo,
                    Inches(15.0),
                    Inches(0.4),
                    height=Inches(0.5),
                    width=Inches(0.5),
                )

                left = Inches(1)
                top = Inches(2)
                width = Inches(12)
                height = Inches(5)

                text_box = slide.shapes.add_textbox(left, top, width, height)

                tb = text_box.text_frame
                lines = textwrap.wrap(
                    dct_form.get("description"),
                    cst_max_word_per_line,
                    break_long_words=False,
                )

                tb.text = "\n".join(lines)

                more_info = dct_form.get("more")
                if more_info:
                    lst_para_more_info = more_info.split("\n\n")
                    for para in lst_para_more_info:
                        prg = tb.add_paragraph()
                        prg.text = " "

                        prg = tb.add_paragraph()

                        lines = textwrap.wrap(
                            para,
                            cst_max_word_per_line,
                            break_long_words=False,
                        )

                        prg.text = "\n".join(lines)

                picture = dct_form.get("picture")
                if picture:
                    picture_filename = f"{uuid.uuid4().hex[:8]}.png"
                    urllib.request.urlretrieve(picture, picture_filename)
                    logo1 = slide.shapes.add_picture(
                        picture_filename,
                        Inches(13.5),
                        Inches(3.4),
                        height=Inches(2),
                        width=Inches(2),
                    )

            # Last Page
            # -----------------------------------------------------------------------------------------------------------------------
            slide = prs.slides.add_slide(prs.slide_layouts[6])

            shape = slide.shapes.add_shape(
                MSO_SHAPE.RECTANGLE, 0, Inches(4.0), Inches(16), Inches(1.0)
            )
            shape.shadow.inherit = False
            fill = shape.fill
            fill.solid()
            fill.fore_color.rgb = RGBColor(255, 0, 0)
            shape.text = "Thank You"
            line = shape.line
            line.color.rgb = RGBColor(255, 0, 0)
            logo1 = slide.shapes.add_picture(
                pylogo,
                Inches(14.5),
                Inches(4.0),
                height=Inches(1.0),
                width=Inches(1.0),
            )
            logo2 = slide.shapes.add_picture(
                pptlogo,
                Inches(15.0),
                Inches(4.0),
                height=Inches(1.0),
                width=Inches(1.0),
            )

            prs.save("proto_1.pptx")
