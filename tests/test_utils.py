import unittest
from unittest import mock

from my_tv_collect.utils import is_vod_playlist


class _FakeResponse:
    def __init__(self, text):
        self._data = text.encode("utf-8")

    def read(self, _max_bytes):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class IsVodPlaylistTests(unittest.TestCase):
    def test_non_m3u8_url_is_never_fetched(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            self.assertFalse(is_vod_playlist("http://example.com/stream.flv"))
            urlopen.assert_not_called()

    def test_endlist_tag_marks_playlist_as_vod(self):
        text = "#EXTM3U\n#EXTINF:5.0,\nseg0.ts\n#EXT-X-ENDLIST\n"
        with mock.patch("urllib.request.urlopen", return_value=_FakeResponse(text)):
            self.assertTrue(is_vod_playlist("http://example.com/clip.m3u8"))

    def test_playlist_type_vod_tag_marks_playlist_as_vod(self):
        text = "#EXTM3U\n#EXT-X-PLAYLIST-TYPE:VOD\n#EXTINF:5.0,\nseg0.ts\n"
        with mock.patch("urllib.request.urlopen", return_value=_FakeResponse(text)):
            self.assertTrue(is_vod_playlist("http://example.com/clip.m3u8"))

    def test_live_playlist_without_endlist_is_not_vod(self):
        text = "#EXTM3U\n#EXT-X-MEDIA-SEQUENCE:8610547\n#EXTINF:6.0,\nseg8610547.ts\n"
        with mock.patch("urllib.request.urlopen", return_value=_FakeResponse(text)):
            self.assertFalse(is_vod_playlist("http://example.com/live.m3u8"))

    def test_fetch_failure_is_treated_as_not_vod(self):
        with mock.patch("urllib.request.urlopen", side_effect=OSError("boom")):
            self.assertFalse(is_vod_playlist("http://example.com/live.m3u8"))


if __name__ == "__main__":
    unittest.main()
