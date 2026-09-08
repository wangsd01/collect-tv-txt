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

    def test_parse_selected_satellite_channels_and_groups_them(self):
        texts = ["浙江卫视高清,http://zj\n东方卫视,http://sh\n广东珠江频道,http://no\n"]
        channels = main.parse_channels(texts)
        self.assertEqual(channels, {"浙江卫视": ["http://zj"], "东方卫视": ["http://sh"]})

        txt, m3u = main.render_outputs(channels)
        self.assertIn("卫视频道,#genre#\n东方卫视,http://sh\n浙江卫视,http://zj", txt)
        self.assertIn('group-title="卫视频道",浙江卫视', m3u)

    def test_same_url_under_different_channels_is_quarantined(self):
        texts = [
            "CCTV1,http://shared\nCCTV2,http://shared\n"
            "CCTV1,http://cctv1-good\nCCTV2,http://cctv2-good\n"
        ]
        self.assertEqual(
            main.parse_cctv_channels(texts),
            {"CCTV1": ["http://cctv1-good"], "CCTV2": ["http://cctv2-good"]},
        )

    def test_channel_aliases_do_not_create_false_url_conflict(self):
        texts = ["CCTV-1,http://same\ncctv1高清,http://same\n"]
        self.assertEqual(main.parse_cctv_channels(texts), {"CCTV1": ["http://same"]})

    def test_cctv4_asia_alias_merges_before_conflict_detection(self):
        texts = ["CCTV4,http://same\nCCTV4ASIA,http://same\n"]
        self.assertEqual(main.parse_cctv_channels(texts), {"CCTV4": ["http://same"]})

    def test_parse_shandong_and_jinan_channels_and_groups_them(self):
        texts = [
            "山东综艺频道,http://zy\n山东生活,http://sh\n"
            "济南新闻综合频道,http://jn\n济南都市,http://ds\n"
            "济南影视,http://ys\n临沂新闻综合,http://no\n"
        ]
        channels = main.parse_channels(texts)
        self.assertNotIn("临沂新闻综合", channels)

        txt, m3u = main.render_outputs(channels)
        self.assertIn("山东频道,#genre#", txt)
        self.assertIn("山东综艺,http://zy", txt)
        self.assertIn("济南频道,#genre#", txt)
        self.assertIn("济南新闻综合,http://jn", txt)
        self.assertIn('group-title="济南频道",济南影视', m3u)

    def test_stability_filter_keeps_only_valid(self):
        values = {"good": ("good", True, 2.0, "OK"), "bad": ("bad", False, 0.0, "TIMEOUT")}
        with mock.patch.object(main, "validate_stream", side_effect=lambda _channel, url, *_: values[url]):
            self.assertEqual(main.stable_channels({"CCTV1": ["bad", "good"]}, workers=2, overrides={}), {"CCTV1": ["good"]})

    def test_validate_stream_rejects_bad_content(self):
        with mock.patch.object(main, "check_stream_tracks", return_value=(True, True, "OK")), \
                mock.patch.object(main, "check_stream_quality", return_value=(False, 1.5, "OK")), \
                mock.patch.object(main, "check_stream_content", return_value=(False, "FROZEN_VIDEO")):
            self.assertEqual(
                main.validate_stream("CCTV1", "http://example", 3, 3, 8),
                ("http://example", False, 1.5, "FROZEN_VIDEO"),
            )

    def test_zero_content_duration_disables_picture_filter(self):
        with mock.patch.object(main, "check_stream_tracks", return_value=(True, True, "OK")), \
                mock.patch.object(main, "check_stream_quality", return_value=(False, 1.5, "OK")), \
                mock.patch.object(main, "check_stream_content", return_value=(True, "OK")) as content:
            self.assertEqual(main.validate_stream("CCTV1", "http://example", 3, 3, 0)[1], True)
            content.assert_called_once_with("http://example", sample_seconds=0, connect_grace=3)

    def test_verified_off_air_stream_is_allowed_when_a_frame_decodes(self):
        overrides = {("CCTV10", "http://off-air"): {"decision": "allow_if_frame"}}
        with mock.patch.object(main, "check_stream_tracks", return_value=(True, True, "OK")), \
                mock.patch.object(main, "check_stream_quality", return_value=(True, 0.0, "DECODE_ERROR")), \
                mock.patch.object(main, "check_stream_frame", return_value=(True, "OK")):
            self.assertEqual(
                main.validate_stream("CCTV10", "http://off-air", 3, 3, 8, overrides),
                ("http://off-air", True, 0.0, "MANUAL_ALLOW"),
            )

    def test_manually_rejected_wrong_channel_is_not_probed(self):
        overrides = {("CCTV6", "http://ad"): {"decision": "reject"}}
        with mock.patch.object(main, "check_stream_quality") as quality:
            self.assertEqual(
                main.validate_stream("CCTV6", "http://ad", 3, 3, 8, overrides)[1], False,
            )
            quality.assert_not_called()

    def test_audio_only_stream_is_rejected_before_decode(self):
        with mock.patch.object(main, "check_stream_tracks", return_value=(False, True, "NO_VIDEO_TRACK")), \
                mock.patch.object(main, "check_stream_quality") as quality:
            self.assertEqual(
                main.validate_stream("山东生活", "http://audio-only", 3, 3, 8),
                ("http://audio-only", False, 0.0, "NO_VIDEO_TRACK"),
            )
            quality.assert_not_called()

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
