import unittest

from scripts.apply_stream_review import apply_reviews


class ApplyStreamReviewTests(unittest.TestCase):
    def test_mixed_content_is_rejected(self):
        entries, applied = apply_reviews([], [{
            "channel": "CCTV12", "url": "http://example/live.m3u8",
            "verdict": "mixed_content", "note": "会插播医疗广告",
        }], "review.json")
        self.assertEqual(applied, 1)
        self.assertEqual(entries[0]["decision"], "reject")
        self.assertEqual(entries[0]["reason"], "会插播医疗广告")

    def test_correct_and_uncertain_do_not_overwrite_rules(self):
        prior = [{"channel": "CCTV1", "url": "http://one", "decision": "reject", "reason": "old"}]
        entries, applied = apply_reviews(prior, [
            {"channel": "CCTV1", "url": "http://one", "verdict": "correct"},
            {"channel": "CCTV2", "url": "http://two", "verdict": "uncertain"},
        ], "review.json")
        self.assertEqual(applied, 0)
        self.assertEqual(entries, prior)
