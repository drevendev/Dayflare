"""Actual HTTP/404 and safety contract for the native M0 acceptance runner."""
from __future__ import annotations
from pathlib import Path
import struct
import tempfile
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen
import zlib

from browser_m0_http import stage, server, changed_query, screenshot_evidence, IMAGES


def png(width):
    def chunk(kind, body):
        return (struct.pack(">I", len(body))+kind+body+
                struct.pack(">I", zlib.crc32(kind+body)&0xffffffff))
    header = struct.pack(">IIBBBBB", width, 1, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",header)+chunk(b"IDAT",zlib.compress(b"\x00"+b"\x00\x00\x00"*width))+chunk(b"IEND",b"")


class HttpAcceptHelpers(unittest.TestCase):
    def test_http_bytes_subpath_and_real_404(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            stage({"index.html":b"valid", "evidence/x.zip":b"abc"},root/"Dayflare")
            with server(root) as address:
                with urlopen(address+"index.html") as response:
                    self.assertEqual((response.status,response.read()),(200,b"valid"))
                with self.assertRaises(HTTPError) as caught:
                    urlopen(address+"absent.zip")
                self.assertEqual(caught.exception.code,404)

    def test_no_traversal_symlink_or_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name in ("../bad","/absolute"):
                with self.assertRaises(ValueError):
                    stage({name:b"bad"},root/"Dayflare")
            stage({"a.txt":b"first"},root/"Dayflare")
            with self.assertRaises(FileExistsError):
                stage({"a.txt":b"second"},root/"Dayflare")
            self.assertEqual((root/"Dayflare/a.txt").read_bytes(),b"first")
            (root/"Dayflare/escape").symlink_to(root,target_is_directory=True)
            with self.assertRaises(ValueError):
                stage({"escape/file":b"bad"},root/"Dayflare")

    def test_version_query_preserves_other_fields(self):
        self.assertEqual(changed_query("http://localhost/Dayflare/?ds=a&s=2&ds=b#comparison","ds","new"),
                         "http://localhost/Dayflare/?s=2&ds=new#comparison")

    def test_screen_inventory_and_png_integrity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name in IMAGES:
                (root/name).write_bytes(png(int(name.split("-")[0])))
            self.assertEqual(set(screenshot_evidence(root)),IMAGES)
            (root/"390-nojs.png").write_bytes(b"wrong")
            with self.assertRaises(AssertionError):
                screenshot_evidence(root)
            (root/"390-nojs.png").write_bytes(png(320))
            with self.assertRaises(AssertionError):
                screenshot_evidence(root)


if __name__=="__main__":
    unittest.main()
