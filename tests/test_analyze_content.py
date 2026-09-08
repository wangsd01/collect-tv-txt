import unittest
import tempfile
from pathlib import Path

from PIL import Image

from scripts.analyze_content import frame_round, text_flags, visually_similar
from scripts.review_stream_content import ReviewItem, card, extract_logo_crops, logo_crop_boxes


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


if __name__ == "__main__":
    unittest.main()
