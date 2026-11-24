# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Load again, from the data files, the proofs whose reference changed
in this version: the contract test the extension renamed, the tests of
the deck program, which live in their own repository, and the tests
ERPLibre renamed or moved since the proofs were written.

The data files are noupdate: an upgrade creates the records it does not
find and leaves the others as they are, so a proof would keep its former
reference. The records listed in REWRITTEN, and the proofs that cite a
repository of MOVED, are loaded again from their file, a hand edit of
them included; every other record keeps its own. Their translations are
dropped but for en_US, so that the loading of the catalogs that follows
this script fills them from the new texts, and a citing field that the
file no longer carries is emptied. The proofs of DELETED, whose test no
repository holds any more, are removed.

The text of a requirement names the deck tests too. Its citations of
them are rewritten in place, by DECK_CITATION: the rest of the text, a
hand edit included, stays.
"""

import copy
import re

from lxml import etree

from odoo import SUPERUSER_ID, api
from odoo.tools import SQL
from odoo.tools.convert import xml_import
from odoo.tools.misc import file_path

MODULE = "erplibre_streamdeck_devops_requirement"

# Data file -> XML ids of its records rewritten in this version: the
# extension's contract 1.5 renamed the test of its version, which these
# proofs cite.
REWRITTEN = {
    "data/requirement_inventory.xml": ("test_sd_inv_r24_1",),
    "data/requirement_control.xml": (
        "test_sd_ctl_r27_1",
        "test_sd_ctl_r66_1",
    ),
    # The proofs whose test ERPLibre or the extension renamed or moved,
    # and the requirements whose proof is gone: those are to do again,
    # their missing work named. A requirement whose name cites a constant
    # or a file the code no longer has takes the name of the file.
    "data/devops_requirement_test.xml": (
        "test_sd_bundle_r01b_1",
        "test_sd_deploy_r29_1",
        "test_sd_deploy_r45_1",
        "test_sd_deploy_r56_1",
        "test_sd_deploy_r73_3",
        "test_sd_grepo_r39_1",
        "test_sd_grepo_r40_1",
        "test_sd_grepo_r40_2",
        "test_sd_grepo_r42_2",
        "test_sd_grepo_r44_1",
        "test_sd_grepo_r47_1",
        "test_sd_grepo_r48_1",
        "test_sd_grepo_r48_2",
        "test_sd_grepo_r50_2",
        "test_sd_grepo_r52_1",
        "test_sd_grepo_r62_27",
        "test_sd_grepo_r88_3",
        "test_sd_gsplit_r07_1",
        "test_sd_gsplit_r11_6",
        "test_sd_gsplit_r24_1",
        "test_sd_plugin_r88_1",
        "test_sd_plugin_r117_5",
        "test_sd_rename_r28_1",
        "test_sd_service_r61_1",
    ),
    "data/devops_requirement.xml": (
        "req_sd_bundle_r05",
        "req_sd_bundle_r05b",
        "req_sd_deploy_r45",
        "req_sd_deploy_r56",
        "req_sd_grepo_r37",
        "req_sd_grepo_r39",
        "req_sd_grepo_r40",
        "req_sd_grepo_r41",
        "req_sd_grepo_r42",
        "req_sd_grepo_r43",
        "req_sd_grepo_r44",
        "req_sd_grepo_r45",
        "req_sd_grepo_r46",
        "req_sd_grepo_r47",
        "req_sd_grepo_r48",
        "req_sd_grepo_r49",
        "req_sd_grepo_r50",
        "req_sd_grepo_r51",
        "req_sd_grepo_r52",
        "req_sd_grepo_r69",
        "req_sd_grepo_r70",
        "req_sd_grepo_r71",
        "req_sd_grepo_r72",
        "req_sd_grepo_r73",
        "req_sd_grepo_r74",
        "req_sd_grepo_r75",
        "req_sd_grepo_r76",
        "req_sd_grepo_r88",
        "req_sd_plugin_r88",
        "req_sd_rename_r28",
        "req_sd_service_r61",
    ),
}

# XML ids of the proofs whose test no longer exists in any repository,
# or does not prove its requirement, removed from the data files: an
# upgrade does not delete a noupdate record on its own.
DELETED = (
    "test_sd_bundle_r05_1",
    "test_sd_bundle_r05_2",
    "test_sd_bundle_r05_3",
    "test_sd_bundle_r05_4",
    "test_sd_bundle_r05b_1",
    "test_sd_bundle_r05b_2",
    "test_sd_grepo_r37_1",
    "test_sd_grepo_r40_3",
    "test_sd_grepo_r41_1",
    "test_sd_grepo_r42_1",
    "test_sd_grepo_r43_1",
    "test_sd_grepo_r45_1",
    "test_sd_grepo_r46_1",
    "test_sd_grepo_r46_2",
    "test_sd_grepo_r47_2",
    "test_sd_grepo_r47_3",
    "test_sd_grepo_r49_1",
    "test_sd_grepo_r50_1",
    "test_sd_grepo_r51_1",
    "test_sd_grepo_r51_2",
    "test_sd_grepo_r69_1",
    "test_sd_grepo_r70_1",
    "test_sd_grepo_r71_1",
    "test_sd_grepo_r71_2",
    "test_sd_grepo_r71_3",
    "test_sd_grepo_r71_4",
    "test_sd_grepo_r72_1",
    "test_sd_grepo_r72_2",
    "test_sd_grepo_r73_1",
    "test_sd_grepo_r73_2",
    "test_sd_grepo_r73_3",
    "test_sd_grepo_r74_1",
    "test_sd_grepo_r75_1",
    "test_sd_grepo_r75_2",
    "test_sd_grepo_r76_1",
)

# Reference prefix -> data files whose proofs citing it are loaded again:
# the tests of the deck program live in their own repository since this
# version, so a proof that names one changed its reference.
MOVED = {
    "erplibre_streamdeck:": (
        "data/devops_requirement_test.xml",
        "data/requirement_control.xml",
    ),
}

# A citation, in the text of a requirement, of a deck test file under
# test/ of ERPLibre: the test files of the deck program, its stubs and
# its fixtures. Of test_streamdeck_entry_points.py, only the classes that
# read the deck program left, for its test_entry_points.py.
DECK_CITATION = re.compile(
    r"(?<![\w-])erplibre:test/("
    r"test_deck_lock\.py|test_erplibre_streamdeck_\w+\.py"
    r"|streamdeck_stubs\.py|fixtures/erplibre_streamdeck/"
    r"|test_streamdeck_entry_points\.py(?=::(?:TestRequirements"
    r"|TestTilerCommandLine|TestControllerCommandLine)\b))"
)
# The text fields of a requirement that cite tests; neither is translated.
CITING_FIELDS = ("achievement", "missing")


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    filenames = list(REWRITTEN)
    filenames += [f for fs in MOVED.values() for f in fs if f not in filenames]
    for filename in filenames:
        xmlids = REWRITTEN.get(filename, ())
        moved = tuple(p for p, files in MOVED.items() if filename in files)
        path = file_path("%s/%s" % (MODULE, filename))
        kept = etree.Element("odoo")
        for record in etree.parse(path).getroot().iter("record"):
            if record.get("id") in xmlids or _cites(record, moved):
                kept.append(copy.deepcopy(record))
        xml_import(
            env, MODULE, {}, "init", noupdate=True, xml_filename=path
        ).parse(kept)
        for record in kept.iter("record"):
            loaded = env.ref("%s.%s" % (MODULE, record.get("id")))
            _keep_english_only(loaded)
            _empty_absent_citing_fields(loaded, record)
    for xmlid in DELETED:
        proof = env.ref("%s.%s" % (MODULE, xmlid), raise_if_not_found=False)
        if proof:
            proof.unlink()
    _follow_deck_citations(env)


def _cites(record, prefixes):
    """True when `record` is a proof whose reference, in the data file,
    starts with one of `prefixes`."""
    if not prefixes or record.get("model") != "devops.requirement.test":
        return False
    reference = record.xpath("string(field[@name='reference'])")
    return reference.startswith(prefixes)


def _empty_absent_citing_fields(loaded, record):
    """Empty the CITING_FIELDS of the requirement `loaded` that its data
    `record` does not carry: loading a record writes only the fields it
    names, and a text the file dropped would stay."""
    if loaded._name != "devops.requirement":
        return
    named = {field.get("name") for field in record.iter("field")}
    absent = {name: False for name in CITING_FIELDS if name not in named}
    if absent:
        loaded.write(absent)


def _deck_path(match):
    """The citation of DECK_CITATION `match` in the deck repository."""
    path = match.group(1)
    if path == "test_streamdeck_entry_points.py":
        path = "test_entry_points.py"
    return "erplibre_streamdeck:tests/%s" % path


def _follow_deck_citations(env):
    """Rewrite each DECK_CITATION in the CITING_FIELDS of the requirements
    of this module; a text without one is not written."""
    ids = (
        env["ir.model.data"]
        .search(
            [("module", "=", MODULE), ("model", "=", "devops.requirement")]
        )
        .mapped("res_id")
    )
    for requirement in env["devops.requirement"].browse(ids).exists():
        values = {}
        for name in CITING_FIELDS:
            text = requirement[name]
            if text:
                rewritten = DECK_CITATION.sub(_deck_path, text)
                if rewritten != text:
                    values[name] = rewritten
        if values:
            requirement.write(values)


def _keep_english_only(record):
    """Drop the translations of the translated fields of `record`, the
    en_US value kept."""
    record.flush_recordset()
    for name, field in record._fields.items():
        if field.translate is not True or not field.store:
            continue
        record.env.cr.execute(
            SQL(
                "UPDATE %s SET %s = jsonb_build_object('en_US', %s->'en_US')"
                " WHERE id = %s AND %s IS NOT NULL",
                SQL.identifier(record._table),
                SQL.identifier(name),
                SQL.identifier(name),
                record.id,
                SQL.identifier(name),
            )
        )
    record.invalidate_recordset()
