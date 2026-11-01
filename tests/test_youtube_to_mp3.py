from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from argparse import Namespace
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = PROJECT_ROOT / "youtube_to_mp3.py"
SPEC = importlib.util.spec_from_file_location("youtube_to_mp3", MODULE_PATH)
assert SPEC and SPEC.loader
downloader = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = downloader
SPEC.loader.exec_module(downloader)


class NormalizeTitleTests(unittest.TestCase):
    def test_removes_old_filename_metadata(self) -> None:
        title = "001. [Shevchenko] Аудіокнига «Іван Підкова». Тарас Шевченко.mp3"
        self.assertEqual(
            downloader.normalize_title(title),
            "аудіокнига іван підкова тарас шевченко",
        )

    def test_removes_youtube_id_and_junk_phrase(self) -> None:
        title = "Книга | Аудіокнига українською [abcdefghijk].mp3"
        self.assertEqual(downloader.normalize_title(title), "книга")


class DuplicateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.known = ["Книга — Частина 1", "Інший твір"]
        self.exact = {downloader.normalize_title(title) for title in self.known}

    def find(self, title: str):
        return downloader.find_duplicate(
            title, self.known, self.exact, threshold=0.94, fuzzy=True
        )

    def test_exact_normalized_duplicate(self) -> None:
        match, score = self.find("КНИГА: частина 1")
        self.assertEqual(match, "Книга — Частина 1")
        self.assertEqual(score, 1.0)

    def test_different_part_number_is_not_duplicate(self) -> None:
        match, _ = self.find("Книга — Частина 2")
        self.assertIsNone(match)


class InputFileTests(unittest.TestCase):
    def test_ignores_comments_and_removes_duplicate_urls(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "playlists.txt"
            path.write_text(
                "# comment\nhttps://example.test/1\n\nhttps://example.test/1\n",
                encoding="utf-8",
            )
            lines = downloader.read_nonempty_lines(path)
            self.assertEqual(downloader.unique_in_order(lines), ["https://example.test/1"])


class YoutubeOptionsTests(unittest.TestCase):
    def test_uses_visionos_without_unstable_pot_fallback(self) -> None:
        args = Namespace(cookies_from_browser=None)
        options = downloader.common_ydl_options(args)
        extractor_args = options["extractor_args"]
        self.assertEqual(extractor_args["youtube"]["player_client"], ["visionos"])
        self.assertNotIn("youtubepot-bgutilscript", extractor_args)
        self.assertTrue(options["force_ipv4"])


class DownloadRetryTests(unittest.TestCase):
    @patch.object(downloader.time, "sleep")
    @patch.object(downloader, "download_video")
    def test_retries_whole_download_after_403(self, download_video: Mock, sleep: Mock) -> None:
        expected = {"title": "Готово"}
        download_video.side_effect = [Exception("HTTP Error 403"), expected]

        result = downloader.download_video_with_retries("https://example.test", Namespace())

        self.assertEqual(result, expected)
        self.assertEqual(download_video.call_count, 2)
        sleep.assert_called_once_with(10)


if __name__ == "__main__":
    unittest.main()
