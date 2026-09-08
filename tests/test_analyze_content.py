import unittest

from scripts.analyze_content import frame_round, text_flags, visually_similar


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


if __name__ == "__main__":
    unittest.main()
