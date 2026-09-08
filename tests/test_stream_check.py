import subprocess
import unittest
from unittest import mock

from my_tv_collect import stream_check


class StreamContentTests(unittest.TestCase):
    def run_check(self, stderr):
        completed = subprocess.CompletedProcess([], 0, stderr=stderr.encode())
        with mock.patch.object(stream_check.subprocess, "run", return_value=completed):
            return stream_check.check_stream_content("http://example", sample_seconds=8)

    def test_rejects_long_black_picture(self):
        self.assertEqual(
            self.run_check("black_start:0 black_end:7 black_duration:7"),
            (False, stream_check.BLACK_SCREEN),
        )

    def test_allows_short_black_transition(self):
        self.assertEqual(
            self.run_check("black_start:1 black_end:2 black_duration:1"),
            (True, stream_check.OK),
        )

    def test_rejects_freeze_marker(self):
        self.assertEqual(
            self.run_check("[freezedetect] freeze_start: 0"),
            (False, stream_check.FROZEN_VIDEO),
        )

    def test_timeout_is_quarantined(self):
        with mock.patch.object(
                stream_check.subprocess, "run", side_effect=subprocess.TimeoutExpired([], 12)):
            self.assertEqual(
                stream_check.check_stream_content("http://example", sample_seconds=8),
                (False, stream_check.TIMEOUT),
            )

    def test_track_probe_rejects_audio_only_stream(self):
        completed = subprocess.CompletedProcess([], 0, stdout=b"audio\n", stderr=b"")
        with mock.patch.object(stream_check.subprocess, "run", return_value=completed):
            self.assertEqual(
                stream_check.check_stream_tracks("http://example"),
                (False, True, stream_check.NO_VIDEO_TRACK),
            )

    def test_track_probe_accepts_video_without_audio(self):
        completed = subprocess.CompletedProcess([], 0, stdout=b"video\n", stderr=b"")
        with mock.patch.object(stream_check.subprocess, "run", return_value=completed):
            self.assertEqual(
                stream_check.check_stream_tracks("http://example"),
                (True, False, stream_check.OK),
            )


if __name__ == "__main__":
    unittest.main()
