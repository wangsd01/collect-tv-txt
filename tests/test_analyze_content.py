import unittest
import tempfile
from pathlib import Path

from PIL import Image

from scripts.analyze_content import frame_round, text_flags, visually_similar
from scripts.review_stream_content import ReviewItem, card, extract_logo_crops, filter_entries, logo_crop_boxes
from my_tv_collect.logo_match import load_logo_library, match_logo_candidates, summarize_logo_matches


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ContentEvidenceTests(unittest.TestCase):
    def test_frame_round_reads_capture_round(self):
        self.assertEqual(frame_round("CCTV1-abc-round-3.jpg"), "3")

    def test_similarity_requires_both_structure_and_colour(self):
        first = {"hash": {"dhash": 10, "mean_rgb": [100, 100, 100]}}
        same = {"hash": {"dhash": 11, "mean_rgb": [105, 103, 102]}}
        different_colour = {"hash": {"dhash": 11, "mean_rgb": [220, 20, 20]}}
        self.assertTrue(visually_similar(first, same))
        self.assertFalse(visually_similar(first, different_colour))

    def test_chinese_sales_words_are_candidates_not_a_verdict(self):
        self.assertEqual(text_flags("限时抢购，订购热线"), ([], ["抢购", "订购", "热线"]))

    def test_logo_crops_cover_each_corner_within_the_frame(self):
        boxes = logo_crop_boxes((1920, 1080))
        self.assertEqual(set(boxes), {"左上", "右上", "左下", "右下"})
        self.assertTrue(all(0 <= x1 < x2 <= 1920 and 0 <= y1 < y2 <= 1080
                            for x1, y1, x2, y2 in boxes.values()))

    def test_logo_crops_are_saved_and_linked_in_the_review_card(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "frame.jpg"
            Image.new("RGB", (100, 50), "red").save(source)
            crops = extract_logo_crops(source, Path(directory) / "logo-crops")
            self.assertEqual(len(crops), 4)
            self.assertTrue(all((Path(directory) / "logo-crops" / crop).exists() for crop in crops))
            markup = card(ReviewItem("CCTV1", "http://one", frames=["frame.jpg"], logo_crops={"frame.jpg": crops}))
            self.assertIn("台标区域（四角）", markup)
            self.assertIn("logo-crops/frame-左上.jpg", markup)

    def test_other_logo_is_a_review_warning_not_a_rejection(self):
        support, warning = summarize_logo_matches(
            "CCTV12", [[{"channel": "CCTV10"}], [{"channel": "CCTV10"}]],
        )
        self.assertEqual(support, "")
        self.assertIn("频道标签分错或内容切换", warning)

    def test_one_other_logo_match_is_treated_as_uncertain(self):
        support, warning = summarize_logo_matches("CCTV12", [[{"channel": "CCTV10"}], []])
        self.assertEqual((support, warning), ("", ""))

    def test_expected_logo_suppresses_other_logo_noise_in_the_same_frames(self):
        frames = [
            [{"channel": "CCTV1"}, {"channel": "CCTV2"}],
            [{"channel": "CCTV1"}, {"channel": "CCTV2"}],
        ]
        support, warning = summarize_logo_matches("CCTV1", frames)
        self.assertIn("目标台标候选", support)
        self.assertEqual(warning, "")

    def test_expected_logo_is_supporting_evidence(self):
        support, warning = summarize_logo_matches("CCTV10", [[{"channel": "CCTV10"}]])
        self.assertIn("目标台标候选", support)
        self.assertEqual(warning, "")

    def test_verified_template_matches_only_as_advisory_evidence(self):
        library = load_logo_library(PROJECT_ROOT / "config" / "logo_templates.json")
        self.assertIn("CCTV10", {entry["channel"] for entry in library})
        with tempfile.TemporaryDirectory() as directory:
            frame = Image.new("RGB", (640, 360), "black")
            with Image.open(PROJECT_ROOT / "config" / "logo_templates" / "CCTV10" / "normal-program.jpg") as logo:
                frame.paste(logo, (10, 10))
            path = Path(directory) / "frame.jpg"
            frame.save(path)
            matches = match_logo_candidates(path, library)
        self.assertEqual(matches[0]["channel"], "CCTV10")

    def test_cctv4_asia_accepts_a_cctv4_logo_candidate(self):
        support, warning = summarize_logo_matches("CCTV4ASIA", [[{"channel": "CCTV4"}]])
        self.assertIn("目标台标候选：CCTV4", support)
        self.assertEqual(warning, "")

    def test_capture_entries_can_be_selected_by_channel_prefix(self):
        entries = [("CCTV1", "http://one"), ("湖南卫视", "http://two")]
        self.assertEqual(filter_entries(entries, channel_prefixes=["CCTV"]), [entries[0]])


if __name__ == "__main__":
    unittest.main()
