# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import unittest

from ..idioms import IdiomContext, classify, split_statements
from ..php import Php


class UpperResolver:
    def trans(self, key, table):
        return key.upper(), key != "Inexact"


CTX = IdiomContext(
    site_key="exemplesite",
    main_lang="en",
    resolver=UpperResolver(),
    table=None,
)
FETCH = (
    "$arr = $websitepage->fetchAll($website->id, 'DESC', 'date_creation',"
    " %s, 0, array('type_container'=>'blogpost', 'status'=>1));"
)
CASES = [
    (
        "includeContainer('header');",
        "INC",
        {"kind": "include", "ref": "header"},
    ),
    ("echo $mysoc->name;", "C1", {"kind": "company", "field": "name"}),
    ("echo $mysoc->email", "C2", {"kind": "company", "field": "email"}),
    ("echo $mysoc->phone;", "C3", {"kind": "company", "field": "phone"}),
    ("echo $mysoc->town;", "C1", {"kind": "company", "field": "city"}),
    (
        "echo $socInfo['email'];",
        "C11",
        {"kind": "company", "field": "email"},
    ),
    (
        "echo $mysoc->getFullAddress(1, '<br>', 1);",
        "C4",
        {"kind": "address"},
    ),
    ("echo urlencode($mysoc->getFullAddress());", "C6", {"kind": "map"}),
    (
        "foreach($mysoc->socialnetworks as $key => $value) { print '<li>'.$key; }",
        "C7",
        {"kind": "social"},
    ),
    (
        "echo getImageFileNameForSize($mysoc->logo_squarred ? $mysoc->logo_squarred : $mysoc->logo, '_small')",
        "C8",
        {"kind": "logo"},
    ),
    ("echo $websitepage->title;", "P1", {"kind": "title"}),
    ("echo ($websitepage->ref == 'about' ? ' active' : '');", "P2", None),
    ("echo newToken();", "R1", {"kind": "drop_element"}),
    (
        "echo dol_escape_htmltag(GETPOST('s', 'alphanohtml'));",
        "R2",
        {"kind": "search_value"},
    ),
    ("print getStructuredData('blogpost', $websitepage);", "S1", None),
    ("$weblangs->loadLangs(array('main','website'));", "T3", None),
    ('$langs->trans("Reservation");', "T3", None),
    ("// echo $website->componentSelectLang('auto', $weblangs);", "T6", None),
    (
        "include_once DOL_DATA_ROOT.'/website/'.$websitekey.'/containers/_library_lib.php'; setSessionLang(); $socInfo = getSocInfo();",
        "L5",
        None,
    ),
    (
        'echo $weblangs->trans("Home");',
        "T1",
        {"kind": "text", "value": "HOME", "key": "Home", "exact": True},
    ),
    (
        "echo $weblangs->defaultlang;",
        "T4",
        {"kind": "text", "value": "en", "key": "", "exact": True},
    ),
    (
        "echo getDolGlobalString('WEBSITE_X') ?: 'Default';",
        "O1",
        {"kind": "text", "value": "Default", "key": "", "exact": True},
    ),
    (
        "echo $website->ref;",
        "REF",
        {"kind": "text", "value": "exemplesite", "key": "", "exact": True},
    ),
    ("echo $blog->title", "G2", {"kind": "blog_field", "field": "title"}),
    ("echo $blog->pageurl", "G2", {"kind": "blog_field", "field": "url"}),
    (
        "echo ($blog->author_alias ? $blog->author_alias : 'anonymous');",
        "G2",
        {"kind": "blog_field", "field": "author"},
    ),
    (
        "$weblangs->load('main'); echo dol_print_date($blog->date_creation, 'daytext', 'tzuser', $weblangs);",
        "G2",
        {"kind": "blog_field", "field": "date"},
    ),
    (
        "echo ($blog->image ? 'viewimage.php?modulepart=medias&file='.$blog->image : 'x');",
        "G2",
        {"kind": "blog_field", "field": "image"},
    ),
    (
        "$MAXNEWS = 3; " + FETCH % "$MAXNEWS" + " foreach($arr as $blog) {",
        "G1",
        {"kind": "blog_loop", "limit": 3},
    ),
    (
        "$fuser = new User($db); "
        + FETCH % "5"
        + " foreach ($arr as $b) { print '<p>'.$b->title.'</p>'; }",
        "G1P",
        {"kind": "blog_list", "limit": 5},
    ),
]
UNKNOWN = [
    "echo $conf->global->MAIN_INFO_GDPR;",
    "$sql = 'SELECT 1'; print $db->query($sql);",
    "echo $mysoc->name; echo $mysoc->email;",
    "$MAXNEWS = $x; " + FETCH % "$MAXNEWS" + " foreach($arr as $blog) {",
    "echo $mysoc->getFullAddress(); system('id');",
    "if ($a) {",
]

HOSTILE = [
    "foreach($mysoc->socialnetworks as $k => $v) { print '<li>'.$k; system('id'); }",
    "foreach($mysoc->socialnetworks as $k => $v) { print system('id'); }",
    FETCH % "5"
    + " foreach ($arr as $b) { print '<p>'.$b->title.'</p>'; system('id'); }",
    FETCH % "5" + " foreach ($arr as $b) { print '<p>'.system('id').'</p>'; }",
    "includeContainer('he ader');",
    "includeContainer('../x');",
    "includeContainer('%s');" % ("a" * 129),
    "$MAXNEWS = \u0663; " + FETCH % "$MAXNEWS" + " foreach($arr as $blog) {",
    "$MAXNEWS = %s; " % ("9" * 5000)
    + FETCH % "$MAXNEWS"
    + " foreach($arr as $blog) {",
    "echo $blog->title; echo $mysoc->name",
    "echo $mysoc->__destruct;",
    "echo $mysoc->name . system('id');",
    "$langs->load('x') . system('id');",
    "setSessionLang() || system('id');",
    "$s = getSocInfo() . system('id');",
    "require 'evil.php' . '_library_lib.php';",
    "print getStructuredData('x') . '<b>visible</b>' . system('id');",
    "if (GETPOST('action') == 'sendmail') { } print $conf->db->pass",
    "if (function_exists('getPagesFromSearchCriterias')) { } print $conf->db->pass",
    "echo ($blog->image ? 'a' : 'b') . $conf->db->pass . ('c')",
    "echo dol_print_date($blog->date_creation) . $conf->db->pass . dol_print_date($x)",
    "echo $conf->db->pass . $mysoc->logo",
    "$M = 3; "
    + (FETCH % "$M").replace("1))", "1)) . system('id')")
    + " foreach($arr as $blog) {",
]


class IdiomsCases:
    def test_table(self):
        for code, idiom, node in CASES:
            decision = classify(Php(code=" %s " % code), CTX)
            self.assertIsNotNone(decision, code)
            self.assertEqual(
                (decision.idiom, decision.node), (idiom, node), code
            )

    def test_unknown(self):
        for code in UNKNOWN:
            self.assertIsNone(classify(Php(code=code), CTX), code)

    def test_regions_and_flags(self):
        r3 = classify(
            Php(
                code="if (GETPOST('action') == 'sendmail') { $to = $mysoc->email;"
            ),
            CTX,
        )
        self.assertEqual(
            (r3.idiom, r3.region, r3.contact_handler), ("R3", "drop", True)
        )
        r6 = classify(
            Php(
                code="$weblangs->load(\"main\"); if (function_exists('getPagesFromSearchCriterias')) { if (1) {"
            ),
            CTX,
        )
        self.assertEqual((r6.idiom, r6.region), ("R6", "drop"))
        g1 = classify(Php(code=CASES[-2][0]), CTX)
        self.assertEqual(g1.region, "loop")
        g2 = classify(Php(code="echo $blog->title"), CTX)
        self.assertTrue(g2.needs_loop)
        s2 = classify(
            Php(
                code="define('__SEO_PAGE_TITLE__', $weblangs->trans('Home'));"
            ),
            CTX,
        )
        self.assertEqual(
            (s2.idiom, s2.seo_title, s2.node), ("S2", "HOME", None)
        )
        lit = classify(
            Php(code='define("__SEO_PAGE_TITLE__", "Our team");'), CTX
        )
        self.assertEqual(lit.seo_title, "Our team")
        inexact = classify(Php(code="echo $weblangs->trans('Inexact');"), CTX)
        self.assertFalse(inexact.exact)
        short = classify(Php(code=" $mysoc->name ", echo=True), CTX)
        self.assertEqual(short.idiom, "C1")

    def test_split_statements(self):
        self.assertEqual(
            split_statements("a('x;y'); foreach ($b as $c) { d(); e(); }; f"),
            ["a('x;y')", "foreach ($b as $c) { d(); e(); }", "f"],
        )

    def test_hostile_values_are_unknown(self):
        for code in HOSTILE:
            self.assertIsNone(classify(Php(code=code), CTX), code[:60])

    def test_ref_and_limit_are_validated(self):
        decision = classify(Php(code="includeContainer('Header-2_x');"), CTX)
        self.assertEqual(decision.node["ref"], "Header-2_x")
        huge = classify(
            Php(code="$M = 99999; " + FETCH % "$M" + " foreach($arr as $b) {"),
            CTX,
        )
        self.assertEqual(huge.node["limit"], 99999)

    def test_free_text_passes_through_raw(self):
        # text.value and seo_title are untrusted: html2arch must escape them.
        raw = "<t t-out=x/>{{x}}"
        o1 = classify(
            Php(code="echo getDolGlobalString('X') ?: '%s'" % raw), CTX
        )
        self.assertEqual((o1.idiom, o1.node["value"]), ("O1", raw))
        seo = "{{7*7}}</title><script>x</script>"
        s2 = classify(
            Php(code="define('__SEO_PAGE_TITLE__', '%s');" % seo), CTX
        )
        self.assertEqual((s2.idiom, s2.seo_title), ("S2", seo))

    def test_logo_ternary_on_blog_image_is_g2(self):
        g2 = classify(
            Php(code="echo ($blog->image ? $blog->image : $mysoc->logo)"), CTX
        )
        self.assertEqual(
            (g2.idiom, g2.node, g2.needs_loop),
            ("G2", {"kind": "blog_field", "field": "image"}, True),
        )


class TestIdioms(IdiomsCases, unittest.TestCase):
    pass
