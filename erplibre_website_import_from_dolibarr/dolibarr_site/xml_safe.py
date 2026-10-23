# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""XML parsing without entity expansion, DTD loading or network access.

Every XML document the module reads goes through this module: SVG media
through parse_xml_safely(), a re-parsed arch through safe_xml_parser().
parse_xml_safely() refuses a document whose DOCTYPE declares an ENTITY
before parsing, whatever the lxml version's defaults; the parsed tree is
checked again for declared entities and entity nodes, because the byte
check cannot see a declaration in UTF-16 or UTF-32.
"""

import re

from lxml import etree

_ENTITY_DECL = re.compile(rb"<!ENTITY", re.I)


def safe_xml_parser(recover=False):
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        huge_tree=False,
        recover=recover,
    )


def parse_xml_safely(data, recover=False):
    if _ENTITY_DECL.search(data):
        raise ValueError("XML entity declarations are refused")
    root = etree.fromstring(data, safe_xml_parser(recover))
    dtd = root.getroottree().docinfo.internalDTD
    if (dtd is not None and any(True for _ in dtd.iterentities())) or any(
        True for _ in root.iter(etree.Entity)
    ):
        raise ValueError("XML entity declarations are refused")
    return root
