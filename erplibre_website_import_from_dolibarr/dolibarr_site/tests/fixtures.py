# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""The invented demo website of the tests, zipped in memory.

Binary media are generated here so the fixture folder holds text only;
the media name with a quote and a parenthesis is added here too.
"""

import io
import pathlib
import struct
import zipfile
import zlib

DEMO = (
    pathlib.Path(__file__).parent
    / "data"
    / "not_supported_files"
    / "site_demo"
)
FILENAME = "website_exemplesite-20260101120000-V24.zip"


def png_bytes():
    """A valid 1x1 RGB PNG."""

    def chunk(kind, data):
        crc = zlib.crc32(kind + data) & 0xFFFFFFFF
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", crc)
        )

    header = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(b"\x00\xff\xff\xff"))
        + chunk(b"IEND", b"")
    )


def webp_bytes():
    payload = b"VP8L" + struct.pack("<I", 5) + b"\x2f\x00\x00\x00\x00\x00"
    return b"RIFF" + struct.pack("<I", 4 + len(payload)) + b"WEBP" + payload


def _drop_insert(sql, ref):
    marker = "__WEBSITE_ID__, '%s', " % ref
    return "\n".join(
        line
        for line in sql.split("\n")
        if not (line.startswith("INSERT") and marker in line)
    )


def demo_files(sql_edit=None, drop_pages=(), extra=None):
    """Files of the demo zip; extra maps more zip names to bytes."""
    files = {}
    for path in sorted(DEMO.rglob("*")):
        if path.is_file():
            files[path.relative_to(DEMO).as_posix()] = path.read_bytes()
    files["medias/image/websitekey/logo.png"] = png_bytes()
    files["medias/image/websitekey/cover.webp"] = webp_bytes()
    files["medias/image/websitekey/bad').png"] = png_bytes()
    sql = files["website_pages.sql"].decode("utf-8")
    for ref in drop_pages:
        sql = _drop_insert(sql, ref)
    if sql_edit:
        sql = sql_edit(sql)
    files["website_pages.sql"] = sql.encode("utf-8")
    files.update(extra or {})
    return files


def demo_zip_bytes(sql_edit=None, drop_pages=(), extra=None):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in demo_files(sql_edit, drop_pages, extra).items():
            zf.writestr(name, data)
    return buf.getvalue()
