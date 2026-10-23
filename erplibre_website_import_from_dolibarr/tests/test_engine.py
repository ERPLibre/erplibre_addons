# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Run the pure engine tests under the Odoo test loader.

The loader keeps only TestCase subclasses defined in this module and, unless
allow_inherited_tests_method is set, only methods of the class's own
__dict__; the tag selector keeps only BaseCase subclasses. Each engine mixin
therefore gets one BaseCase subclass here.
"""

from odoo.tests.common import BaseCase

from ..dolibarr_site.tests.test_analysis import AnalyseCases, BuildCases
from ..dolibarr_site.tests.test_engine_isolation import EngineIsolationCases
from ..dolibarr_site.tests.test_html2arch import CleanCases, RenderCases
from ..dolibarr_site.tests.test_idioms import IdiomsCases
from ..dolibarr_site.tests.test_langs import LangsCases
from ..dolibarr_site.tests.test_layout import LayoutCases
from ..dolibarr_site.tests.test_messages import MessagesCases
from ..dolibarr_site.tests.test_model import ModelCases
from ..dolibarr_site.tests.test_php import AssembleCases, TokenizeCases
from ..dolibarr_site.tests.test_render_site import RenderSiteCases
from ..dolibarr_site.tests.test_sqldump import SqldumpCases
from ..dolibarr_site.tests.test_stock_templates import StockTemplatesCases
from ..dolibarr_site.tests.test_urls_css import CssCases, UrlsCases
from ..dolibarr_site.tests.test_validate import ValidateCases
from ..dolibarr_site.tests.test_zipsource import ZipsourceCases


class TestEngineIsolation(EngineIsolationCases, BaseCase):
    allow_inherited_tests_method = True


class TestMessages(MessagesCases, BaseCase):
    allow_inherited_tests_method = True


class TestModel(ModelCases, BaseCase):
    allow_inherited_tests_method = True


class TestValidate(ValidateCases, BaseCase):
    allow_inherited_tests_method = True


class TestSqldump(SqldumpCases, BaseCase):
    allow_inherited_tests_method = True


class TestZipsource(ZipsourceCases, BaseCase):
    allow_inherited_tests_method = True


class TestTokenize(TokenizeCases, BaseCase):
    allow_inherited_tests_method = True


class TestAssemble(AssembleCases, BaseCase):
    allow_inherited_tests_method = True


class TestLangs(LangsCases, BaseCase):
    allow_inherited_tests_method = True


class TestIdioms(IdiomsCases, BaseCase):
    allow_inherited_tests_method = True


class TestClean(CleanCases, BaseCase):
    allow_inherited_tests_method = True


class TestUrls(UrlsCases, BaseCase):
    allow_inherited_tests_method = True


class TestCss(CssCases, BaseCase):
    allow_inherited_tests_method = True


class TestLayout(LayoutCases, BaseCase):
    allow_inherited_tests_method = True


class TestRender(RenderCases, BaseCase):
    allow_inherited_tests_method = True


class TestBuild(BuildCases, BaseCase):
    allow_inherited_tests_method = True


class TestAnalyse(AnalyseCases, BaseCase):
    allow_inherited_tests_method = True


class TestRenderSite(RenderSiteCases, BaseCase):
    allow_inherited_tests_method = True


class TestStockTemplates(StockTemplatesCases, BaseCase):
    allow_inherited_tests_method = True
