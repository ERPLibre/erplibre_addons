# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import unittest

from ..php import (
    Decision,
    Html,
    Php,
    assemble,
    block_role,
    mask,
    neutralise,
    normalise,
    pair,
    strip_comments,
    tokenize,
    top_level_blocks,
)


def blocks(content):
    return [t for t in tokenize(content) if isinstance(t, Php)]


class TokenizeCases:
    def test_contexts(self):
        cases = [
            ("<p><?php echo 1; ?></p>", "text", ""),
            (
                '<a href="mailto:<?php echo $mysoc->email; ?>">',
                "attribute",
                "href",
            ),  # noqa: E501
            ("<img src=<?php echo $x ?>>", "attribute", "src"),
            ("<script>var a='<?php echo 1 ?>';</script>", "script", "script"),
            ("<style>b{color:<?php echo 1 ?>}</style>", "script", "style"),
            ("<div <?php echo 'x' ?> class='a'>", "tag", ""),
            ("<!-- <?php echo 1 ?> -->", "text", ""),
            ("<script>x</script><b><?php echo 1 ?></b>", "text", ""),
            (
                '<div class=<?php echo 1 ?> title="<?php echo 2 ?>">',
                "attribute",
                "title",
            ),  # noqa: E501
            ("<img src=a<?php echo 1 ?>b>", "attribute", "src"),
            ("<a title='it' href=\"<?php echo 2 ?>\">", "attribute", "href"),
        ]
        for content, context, attr in cases:
            block = blocks(content)[-1]
            self.assertEqual(
                (block.context, block.attr), (context, attr), content
            )  # noqa: E501

    def test_block_ends(self):
        (block,) = blocks('<?php echo "?>"; ?>after')
        self.assertEqual(block.code, ' echo "?>"; ')
        tokens = tokenize("<?php // note ?>after")
        self.assertEqual(tokens[0].code, " // note ")
        self.assertEqual(tokens[1].text, "after")
        (block,) = blocks("<?php /* ?> */ echo 1; ?>")
        self.assertEqual(block.code, " /* ?> */ echo 1; ")
        (block,) = blocks("<?php # hash ?>x")
        self.assertEqual(block.code, " # hash ")

    def test_unclosed_last_block_runs_to_end(self):
        (block,) = blocks("<p>a</p>\n<?php echo 1;\n<p>b</p>")
        self.assertFalse(block.closed)
        self.assertEqual(block.code, " echo 1;\n<p>b</p>")
        self.assertEqual(block.line, 2)

    def test_short_echo_and_xml_pi(self):
        (block,) = blocks("<?= $x ?>")
        self.assertTrue(block.echo)
        tokens = tokenize('<?xml version="1.0"?><p/>')
        self.assertEqual([type(t) for t in tokens], [Html])

    def test_round_trip_of_html_parts(self):
        content = "<p>a</p><?php echo 1; ?><p>b</p>"
        html = "".join(
            t.text for t in tokenize(content) if isinstance(t, Html)
        )  # noqa: E501
        self.assertEqual(html, "<p>a</p><p>b</p>")

    def test_comment_helpers(self):
        code = "echo '{' . \"}\"; // }\n/* { */ if ($a) {"
        self.assertEqual(mask(code).count("{"), 1)
        self.assertEqual(
            strip_comments(code), "echo '{' . \"}\"; \n  if ($a) {"
        )

    def test_hostile_input_terminates(self):
        big = 20000
        for content in (
            "<?php " + "'" * big,
            "<?php " + "/*" * big,
            "<a " + "=" * big + "<?php echo 1 ?>",
            "<script>" * big + "<?php echo 1 ?>",
            "<!--" * big + "<?php 1 ?>",
            "<?php 1 ?>" * big,
        ):
            tokenize(content)
        self.assertEqual(len(blocks("<?php 1 ?>\n" * big)), big)
        self.assertEqual(blocks("<?php 1 ?>\n" * 3)[2].line, 3)


class TestTokenize(TokenizeCases, unittest.TestCase):
    pass


def size(text):
    return len(text.encode("utf-8"))


def known(tokens, **by_code):
    """Decisions for blocks whose normalised code is a key of by_code."""
    decisions = {}
    for idx, tok in enumerate(tokens):
        if isinstance(tok, Php):
            decisions[idx] = by_code.get(normalise(tok.code))
    return decisions


class AssembleCases:
    def test_block_roles(self):
        self.assertEqual(block_role(" if ($a) { "), ("open", 1))
        self.assertEqual(block_role("} else {"), ("middle", 0))
        self.assertEqual(block_role("}"), ("close", 1))
        self.assertEqual(block_role("} }"), ("close", 2))
        self.assertEqual(block_role("foreach ($a as $b):"), ("open", 1))
        self.assertEqual(block_role("else:"), ("middle", 0))
        self.assertEqual(block_role("endforeach;"), ("close", 1))
        self.assertEqual(block_role("echo '{';"), ("none", 0))

    def test_pair(self):
        tokens = tokenize(
            "<?php if ($a) { ?>A<?php } else { ?>B<?php } ?>"
            "<?php foreach ($x as $y): ?>C<?php endforeach; ?>"
            "<?php } ?><?php while ($z) { ?>"
        )
        pairing = pair(tokens)
        spans = sorted((r.open, r.close) for r in pairing.regions)
        self.assertEqual(spans, [(0, 4), (5, 7)])
        self.assertEqual(pairing.regions[0].middles, [2])
        self.assertEqual(len(pairing.orphans), 1)
        self.assertEqual(len(pairing.unbalanced), 1)
        self.assertEqual(top_level_blocks(tokens), [0, 4, 5, 7, 8, 9])

    def test_unknown_region_removed_with_bytes(self):
        inner_a, inner_b = "<p>REMOVED-MARKER</p>", "<p>else</p>"
        content = (
            "<div>keep</div><?php if ($x) { ?>%s<?php } else { ?>%s"
            "<?php } ?><div>tail</div>" % (inner_a, inner_b)
        )
        tokens = tokenize(content)
        asm = assemble(tokens, known(tokens))
        self.assertEqual(asm.html, "<div>keep</div><div>tail</div>")
        self.assertEqual(asm.removed_bytes, size(inner_a) + size(inner_b))
        self.assertEqual(asm.unknown_blocks, 1)
        self.assertEqual(asm.removed[0]["bytes"], asm.removed_bytes)
        self.assertEqual(asm.warnings, [])

    def test_unbalanced_and_orphan(self):
        tokens = tokenize("<?php if ($a) { ?><p>stay</p><?php } ?><?php } ?>")
        asm = assemble(tokens, known(tokens))
        self.assertEqual(asm.html, "")
        tokens = tokenize(
            "<p>a</p><?php } ?><p>b</p><?php if ($q) { ?><p>c</p>"
        )  # noqa: E501
        asm = assemble(tokens, known(tokens))
        self.assertEqual(asm.html, "<p>a</p><p>b</p><p>c</p>")
        self.assertEqual(
            sorted(code for code, _line in asm.warnings),
            ["php_unbalanced", "php_unpaired"],
        )
        self.assertEqual(asm.removed_bytes, 0)

    def test_attribute_and_script_contexts(self):
        tokens = tokenize('<a href="<?php echo $u ?>">t</a>')
        self.assertEqual(assemble(tokens, known(tokens)).html, "<a>t</a>")
        tokens = tokenize('<a href="/p?<?php echo $u ?>">t</a>')
        self.assertEqual(
            assemble(tokens, known(tokens)).html, '<a href="/p?">t</a>'
        )
        script = "<script>var a='<?php echo $u ?>';</script>"
        tokens = tokenize("<p>x</p>" + script + "<p>y</p>")
        asm = assemble(tokens, known(tokens))
        self.assertEqual(asm.html, "<p>x</p><p>y</p>")
        self.assertEqual(
            asm.removed_bytes, size(script) - size("<?php echo $u ?>")
        )  # noqa: E501
        self.assertEqual(asm.removed[0]["context"], "script")

    def test_known_blocks_become_markers(self):
        name = Decision("C1", node={"kind": "company", "field": "name"})
        email = Decision("C2", node={"kind": "company", "field": "email"})
        silent = Decision("T3")
        tokens = tokenize(
            "<?php $weblangs->load('main'); ?><b><?php echo $mysoc->name; ?>"
            '</b><a href="mailto:<?php echo $mysoc->email ?>">m</a>'
        )
        asm = assemble(
            tokens,
            known(
                tokens,
                **{
                    "$weblangs->load('main')": silent,
                    "echo $mysoc->name": name,
                    "echo $mysoc->email": email,
                },
            ),
        )
        self.assertEqual(
            asm.html,
            '<b><dolibarr-q id="1"></dolibarr-q></b>'
            '<a href="mailto:DOLIBARRQ2Q">m</a>',
        )
        self.assertEqual(asm.nodes["2"]["field"], "email")
        self.assertEqual(asm.unknown_blocks, 0)
        self.assertNotIn("line", email.node, "the decision is not mutated")

    def test_loop_and_drop_regions(self):
        loop = Decision(
            "G1", node={"kind": "blog_loop", "limit": 3}, region="loop"
        )  # noqa: E501
        field = Decision(
            "G2",
            node={"kind": "blog_field", "field": "title"},
            needs_loop=True,
        )  # noqa: E501
        drop = Decision("R3", region="drop", contact_handler=True)
        content = (
            "<?php foreach ($blogs as $blog) { ?>\n"
            "<h3><?php echo $blog->title ?></h3>\n"
            "<?php } ?><?php echo $blog->title ?>\n"
            "<?php if (GETPOST('action') == 'sendmail') { ?><p>sent</p>\n"
            "<?php } ?><p>end</p>"
        )
        tokens = tokenize(content)
        asm = assemble(
            tokens,
            known(
                tokens,
                **{
                    "foreach ($blogs as $blog) {": loop,
                    "echo $blog->title": field,
                    "if (GETPOST('action') == 'sendmail') {": drop,
                },
            ),
        )
        self.assertEqual(
            asm.html,
            '<dolibarr-loop id="1">\n<h3><dolibarr-q id="2"></dolibarr-q></h3>'
            "\n</dolibarr-loop>\n<p>end</p>",
        )
        self.assertEqual(asm.unknown_blocks, 1, "field outside the loop")
        drop_entry = asm.removed[-1]
        self.assertEqual(drop_entry["bytes"], size("<p>sent</p>\n"))
        self.assertEqual(drop_entry["line"], 4)
        self.assertEqual(
            drop_entry["code"], "if (GETPOST('action') == 'sendmail') {"
        )
        self.assertEqual(asm.removed[0]["line"], 3, "the stray field")
        self.assertEqual(asm.removed_bytes, size("<p>sent</p>\n"))
        self.assertEqual(asm.nodes["1"]["line"], 1)
        self.assertEqual(asm.nodes["2"]["line"], 2)

    def test_drop_without_closer_is_recorded(self):
        drop = Decision("R3", region="drop", contact_handler=True)
        tokens = tokenize(
            "<p>a</p>\n<?php if (GETPOST('action') == 'sendmail') { ?>"
            "<p>kept</p>"
        )
        asm = assemble(
            tokens,
            known(tokens, **{"if (GETPOST('action') == 'sendmail') {": drop}),
        )
        self.assertEqual(asm.html, "<p>a</p>\n<p>kept</p>")
        self.assertEqual(len(asm.removed), 1)
        self.assertEqual(asm.removed[0]["line"], 2)
        self.assertEqual(asm.removed[0]["bytes"], 0)
        self.assertEqual(asm.unknown_blocks, 0)

    def test_marker_lookalikes_are_neutralised(self):
        tokens = tokenize(
            '<dolibarr-q id="1"></dolibarr-q><p class="DOLIBARRQ1Q">'
            "<Dolibarr-Loop>x</Dolibarr-Loop></p>"
        )
        html = assemble(tokens, {}).html
        self.assertNotIn("dolibarr-q", html.lower())
        self.assertNotIn("dolibarr-loop", html.lower())
        self.assertNotIn("DOLIBARRQ1Q", html)
        self.assertEqual(neutralise("DOLIBARRQ7Q"), "DOLIBARRX7X")
        self.assertEqual(neutralise("DOLIBARR&#81;7Q"), "DOLIBARRX7X")
        self.assertEqual(neutralise("&#x44;OLIBARR&#x51;7&#81"), "DOLIBARRX7X")
        self.assertEqual(neutralise("a &#60; b &#38;"), "a &#60; b &#38;")

    def test_normalise(self):
        self.assertEqual(
            normalise(' echo  $weblangs->trans("Home") ; // c\n'),
            "echo $weblangs->trans('Home')",
        )

    def test_secret_blocks_reported_without_code(self):
        tokens = tokenize("<?php $k = dol_hash('seed'.$x); echo $k; ?>")
        asm = assemble(tokens, {})
        self.assertEqual(asm.removed[0]["code"], "(secret-bearing block)")

    def test_lookalikes_cannot_be_spliced_around_a_block(self):
        silent = Decision("T3")
        cases = [
            ('<p class="DOLIBARRQ<?php foo() ?>1Q">', {}),
            (
                '<dolibarr-<?php foo() ?>q id="1"></dolibarr-<?php foo() ?>q>',
                {},
            ),
            (
                '<dolibarr-<?php $weblangs->load("x") ?>loop id="1">x',
                {"$weblangs->load('x')": silent},
            ),
            ("DOLIBARRQ<?php if ($a) { ?>zz<?php } ?>1Q", {}),
        ]
        for content, by_code in cases:
            tokens = tokenize(content)
            html = assemble(tokens, known(tokens, **by_code)).html
            self.assertNotIn("dolibarr-q", html.lower(), content)
            self.assertNotIn("dolibarr-loop", html.lower(), content)
            self.assertNotIn("DOLIBARRQ1Q", html, content)
            self.assertNotIn("\x00", html)

    def test_skipped_region_does_not_swallow_loop_closer(self):
        loop = Decision("G1", node={"kind": "blog_loop"}, region="loop")
        drop = Decision("R3", region="drop")
        for inner, by_code in (
            ("if ($c) {", {}),
            ("if ($c) {", {"if ($c) {": drop}),
        ):
            tokens = tokenize(
                "<?php foreach ($blogs as $blog) { ?><h3>a</h3>"
                "<?php %s ?>X<?php } } ?><p>after</p>" % inner
            )
            by_code = dict(by_code, **{"foreach ($blogs as $blog) {": loop})
            html = assemble(tokens, known(tokens, **by_code)).html
            self.assertEqual(
                html,
                '<dolibarr-loop id="1"><h3>a</h3></dolibarr-loop>'
                "<p>after</p>",
            )

    def test_script_removal_starts_at_its_own_tag(self):
        tokens = tokenize(
            "<p>before</p><script>document.write('<script src=x></scr'"
            "+'ipt>'); var a='<?php echo $u ?>';</script><p>after</p>"
        )
        asm = assemble(tokens, known(tokens))
        self.assertEqual(asm.html, "<p>before</p><p>after</p>")
        self.assertEqual(asm.removed[0]["context"], "script")

    def test_script_cut_ignores_an_earlier_script(self):
        silent = Decision("T3")
        tokens = tokenize(
            "<script>var k='<?php $weblangs->load('x') ?>';</script>"
            "<p>keep</p><?php if($c){ ?><script><?php } ?>"
            "var a='<?php echo $u ?>';</script><p>after</p>"
        )
        html = assemble(
            tokens, known(tokens, **{"$weblangs->load('x')": silent})
        ).html
        self.assertIn("<p>keep</p>", html)
        self.assertIn("<p>after</p>", html)
        self.assertNotIn("var a", html)

    def test_loop_closer_inside_a_removed_script_still_closes(self):
        loop = Decision("G1", node={"kind": "blog_loop"}, region="loop")
        opener = {"foreach ($blogs as $blog) {": loop}
        for body in (
            "<script>var a='<?php echo $u ?>';<?php } ?></script>",
            "<script>a<?php } ?>b<?php echo $u ?></script>",
        ):
            tokens = tokenize(
                "<?php foreach ($blogs as $blog) { ?>%s<p>after</p>" % body
            )
            html = assemble(tokens, known(tokens, **opener)).html
            self.assertEqual(
                html,
                '<dolibarr-loop id="1"></dolibarr-loop><p>after</p>',
                body,
            )


class TestAssemble(AssembleCases, unittest.TestCase):
    pass
