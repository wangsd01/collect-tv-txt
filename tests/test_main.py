import tempfile
import unittest
from pathlib import Path
from unittest import mock

import main


class MainTests(unittest.TestCase):
    def test_parse_txt_and_m3u_deduplicates_and_filters(self):
        texts = ["cctv1高清,http://one\n湖南卫视,http://no\n",
                 "#EXTM3U\n#EXTINF:-1,CCTV-1\nhttp://one\n#EXTINF:-1,CCTV2财经\nhttp://two$note\n"]
        self.assertEqual(main.parse_cctv_channels(texts), {"CCTV1": ["http://one"], "CCTV2": ["http://two"]})

    def test_stability_filter_keeps_only_valid(self):
        values = {"good": ("good", True, 2.0), "bad": ("bad", False, 0.0)}
        with mock.patch.object(main, "validate_stream", side_effect=lambda url, *_: values[url]):
            self.assertEqual(main.stable_channels({"CCTV1": ["bad", "good"]}, workers=2), {"CCTV1": ["good"]})

    def test_total_failure_does_not_overwrite_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            txt, m3u = Path(directory) / "a.txt", Path(directory) / "a.m3u"
            txt.write_text("old", encoding="utf-8"); m3u.write_text("old", encoding="utf-8")
            with mock.patch.object(main, "SOURCE_URLS", ["https://invalid"]), mock.patch.object(main, "fetch_source", side_effect=TimeoutError()):
                self.assertEqual(main.main(["--output-txt", str(txt), "--output-m3u", str(m3u)]), 1)
            self.assertEqual(txt.read_text(encoding="utf-8"), "old"); self.assertEqual(m3u.read_text(encoding="utf-8"), "old")

    def test_render_m3u_pairs(self):
        _, m3u = main.render_outputs({"CCTV2": ["http://two"], "CCTV1": ["http://one"]})
        self.assertEqual(m3u.splitlines()[0], "#EXTM3U")
        self.assertEqual(m3u.splitlines()[1:], ['#EXTINF:-1 group-title="央视频道",CCTV1', "http://one", '#EXTINF:-1 group-title="央视频道",CCTV2', "http://two"])

