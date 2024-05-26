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
from pptx.enum.dml import MSO_THEME_COLOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Inches, Pt

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class DevopsPlanProjectPptx(models.Model):
    _name = "devops.plan.project.pptx"
    _description = "devops_plan_project_pptx"

    name = fields.Char()

    data = fields.Text()

    title = fields.Char()

    subtitle = fields.Char()

    @api.multi
    def execute(self):
        cst_max_word_per_line = 80
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

            title = ""
            if rec.title:
                rec_title = rec.title[0].upper() + rec.title[1:]
                if rec.subtitle:
                    rec_subtitle = rec.subtitle[0].upper() + rec.subtitle[1:]
                    title = f"{rec_title}\n            {rec_subtitle}"
                else:
                    title = rec_title

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
            # logo1 = slide.shapes.add_picture(
            #     pylogo,
            #     Inches(13.8),
            #     Inches(6.0),
            #     height=Inches(1.0),
            #     width=Inches(1.0),
            # )
            # logo2 = slide.shapes.add_picture(
            #     pptlogo,
            #     Inches(14.5),
            #     Inches(5.8),
            #     height=Inches(1.5),
            #     width=Inches(1.5),
            # )
            logo2 = slide.shapes.add_picture(
                pptlogo,
                Inches(14.5),
                Inches(6.0),
                height=Inches(1.1),
                width=Inches(1.1),
            )

            # Content pages
            lst_formation = dct_formation.get("formation")
            for no_page, dct_form in enumerate(lst_formation):
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
                # logo1 = slide.shapes.add_picture(
                #     pylogo,
                #     Inches(14.5),
                #     Inches(0.4),
                #     height=Inches(0.5),
                #     width=Inches(0.5),
                # )
                logo2 = slide.shapes.add_picture(
                    pptlogo,
                    Inches(15.0),
                    Inches(0.4),
                    height=Inches(0.5),
                    width=Inches(0.5),
                )

                # Add picture
                picture = dct_form.get("picture")
                if picture:
                    picture_filename = f"{uuid.uuid4().hex[:8]}.png"
                    urllib.request.urlretrieve(picture, picture_filename)
                    picture_slide = slide.shapes.add_picture(
                        picture_filename,
                        Inches(11.5),
                        Inches(3.4),
                        height=Inches(4),
                        width=Inches(4),
                    )

                # Add content
                left = Inches(1)
                top = Inches(2)
                width = Inches(10)
                height = Inches(5)

                text_box = slide.shapes.add_textbox(left, top, width, height)

                tb = text_box.text_frame
                lines = textwrap.wrap(
                    dct_form.get("description"),
                    cst_max_word_per_line,
                    break_long_words=False,
                )

                # wrapper = textwrap.TextWrapper(width=50)
                #
                # dedented_text = textwrap.dedent(text=sample_text)
                # original = wrapper.fill(text=dedented_text)
                #
                # print('Original:\n')
                # print(original)
                #
                # shortened = textwrap.shorten(text=original, width=100)
                # shortened_wrapped = wrapper.fill(text=shortened)
                #
                # print('\nShortened:\n')
                # print(shortened_wrapped)

                tb.text = "\n".join(lines)

                content_short = dct_form.get("short_vulgarisation")
                if content_short:
                    lst_para_more_info = content_short.split("\n")
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

                # Add page number
                left = Inches(15.1)
                top = Inches(8.5)
                width = Inches(0.5)
                height = Inches(0.5)

                text_box = slide.shapes.add_textbox(left, top, width, height)

                tb = text_box.text_frame
                p = tb.paragraphs[0]
                run = p.add_run()
                # tb.text = f"{no_page + 1}"
                run.text = f"{no_page + 1}"

                font = run.font
                font.name = "Calibri"
                font.size = Pt(18)
                font.bold = True
                font.italic = None  # cause value to be inherited from theme
                font.color.theme_color = MSO_THEME_COLOR.ACCENT_1

                # Add slide note
                more_info = dct_form.get("more")
                if more_info:
                    notes_slide = slide.notes_slide
                    text_frame = notes_slide.notes_text_frame
                    text_frame.text = more_info

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
            # logo1 = slide.shapes.add_picture(
            #     pylogo,
            #     Inches(14.5),
            #     Inches(4.0),
            #     height=Inches(1.0),
            #     width=Inches(1.0),
            # )
            logo2 = slide.shapes.add_picture(
                pptlogo,
                Inches(15.0),
                Inches(4.0),
                height=Inches(1.0),
                width=Inches(1.0),
            )

            prs.save("proto_1.pptx")
