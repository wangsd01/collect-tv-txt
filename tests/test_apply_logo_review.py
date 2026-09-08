import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from scripts.apply_logo_review import apply_logo_reviews, apply_wrong_logo_reviews, normalized_crop_box
from scripts.logo_template_review import select_diverse_frames


class ApplyLogoReviewTests(unittest.TestCase):
    def test_normalized_crop_box(self):
        self.assertEqual(normalized_crop_box([.1, .2, .4, .5], (1000, 500)), (100, 100, 400, 250))

    def test_only_confirmed_box_becomes_a_template(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); frames = root / "capture" / "frames"; frames.mkdir(parents=True)
            Image.new("RGB", (100, 50), "white").save(frames / "one.jpg")
            config = root / "config" / "logo_templates.json"; config.parent.mkdir()
            config.write_text("[]", encoding="utf-8")
            payload = {"schema_version": 1, "reviews": [
                {"channel": "CCTV1", "frame": "one.jpg", "verdict": "correct_logo", "box": [.1, .1, .5, .5]},
                {"channel": "CCTV2", "frame": "two.jpg", "verdict": "wrong_logo"},
            ]}
            entries, created = apply_logo_reviews(payload, root / "capture", config)
            self.assertEqual(created, 1)
            self.assertEqual(entries[0]["channel"], "CCTV1")
            self.assertTrue((config.parent / entries[0]["file"]).is_file())

    def test_parent_path_cannot_escape_capture_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / "capture" / "frames").mkdir(parents=True)
            Image.new("RGB", (100, 50), "white").save(root / "outside.jpg")
            payload = {"schema_version": 1, "reviews": [{
                "channel": "CCTV1", "frame": "../../outside.jpg",
                "verdict": "correct_logo", "box": [.1, .1, .5, .5],
            }]}
            with self.assertRaises(ValueError):
                apply_logo_reviews(payload, root / "capture", root / "config.json")

    def test_synchronized_frames_are_reduced_to_one_representative(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); frames = root / "frames"; frames.mkdir()
            Image.new("RGB", (100, 50), "red").save(frames / "one.jpg")
            Image.new("RGB", (100, 50), "red").save(frames / "two.jpg")
            Image.new("RGB", (100, 50), "blue").save(frames / "three.jpg")
            manifest = {"items": [
                {"channel": "CCTV1", "url": "http://one", "frames": ["one.jpg"], "captured_at": ["1"]},
                {"channel": "CCTV1", "url": "http://two", "frames": ["two.jpg", "three.jpg"], "captured_at": ["2", "3"]},
            ]}
            representatives = select_diverse_frames(manifest, root)
            self.assertEqual(len(representatives), 2)
            self.assertEqual(representatives[0]["duplicate_count"], 2)
            self.assertEqual(len(representatives[0]["duplicate_urls"]), 2)

    def test_wrong_logo_is_a_human_rejection_and_alias_is_normalized(self):
        payload = {"reviews": [{
            "channel": "CCTV4ASIA", "url": "http://wrong", "frame": "one.jpg",
            "verdict": "wrong_logo", "reviewed_at": "now",
        }]}
        entries, applied = apply_wrong_logo_reviews(payload, [], "review.json")
        self.assertEqual(applied, 1)
        self.assertEqual(entries[0]["channel"], "CCTV4")
        self.assertEqual(entries[0]["decision"], "reject")


if __name__ == "__main__":
    unittest.main()
