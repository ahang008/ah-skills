from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "download_douyin.py"
SPEC = importlib.util.spec_from_file_location("download_douyin", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class DownloaderTests(unittest.TestCase):
    def test_extract_share_url_from_full_command(self) -> None:
        text = "3.58 abc:/ 测试 https://v.douyin.com/AbC_123/ 复制此链接"
        self.assertEqual(MODULE.extract_share_url(text), "https://v.douyin.com/AbC_123/")

    def test_rejects_spoofed_domain_and_http(self) -> None:
        with self.assertRaises(MODULE.DownloadError):
            MODULE.extract_share_url("https://v.douyin.com.example.org/abc/")
        with self.assertRaises(MODULE.DownloadError):
            MODULE.extract_share_url("http://v.douyin.com/abc/")

    def test_extracts_video_id_from_path_and_modal(self) -> None:
        self.assertEqual(
            MODULE.extract_video_id("https://www.douyin.com/video/7123456789012345678"),
            "7123456789012345678",
        )
        self.assertEqual(
            MODULE.extract_video_id("https://www.douyin.com/jingxuan?modal_id=7123456789012345678"),
            "7123456789012345678",
        )

    def test_selects_play_source_and_ignores_download_addr(self) -> None:
        fixture = ROOT / "tests" / "fixtures" / "aweme_feed.json"
        payload = json.loads(fixture.read_text(encoding="utf-8"))
        item = MODULE.parse_metadata(payload, "7123456789012345678")
        sources = MODULE.media_sources(item)
        self.assertEqual(sources[0]["name"], "play_addr_h264")
        self.assertTrue(all("watermark" not in row["url"] for row in sources))
        self.assertTrue(all(row["name"] != "download_addr" for row in sources))

    def test_rejects_private_and_local_media_urls(self) -> None:
        self.assertFalse(MODULE.valid_media_url("https://127.0.0.1/video.mp4"))
        self.assertFalse(MODULE.valid_media_url("https://10.0.0.8/video.mp4"))
        self.assertFalse(MODULE.valid_media_url("https://host.local/video.mp4"))
        self.assertTrue(MODULE.valid_media_url("https://cdn.example.test/video.mp4"))

    def test_safe_title_and_unique_output(self) -> None:
        self.assertEqual(MODULE.safe_title('  A/B:*? "测试"  '), "AB 测试")
        with tempfile.TemporaryDirectory() as temp_name:
            output_dir = Path(temp_name)
            first = MODULE.unique_output_path(output_dir, "标题", "7123456789012345678")
            first.touch()
            second = MODULE.unique_output_path(output_dir, "标题", "7123456789012345678")
            self.assertNotEqual(first, second)
            self.assertTrue(second.name.endswith("-2.mp4"))

    def test_author_folder_is_created_and_reused(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            library = Path(temp_name) / "抖音无水印视频"
            first = MODULE.ensure_author_directory(library, "柱子哥TzFilm")
            second = MODULE.ensure_author_directory(library, "柱子哥TzFilm")
            self.assertEqual(first, second)
            self.assertEqual(first.parent, library.resolve())
            self.assertTrue(first.is_dir())

    def test_author_folder_cannot_escape_library(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            library = Path(temp_name) / "library"
            author_dir = MODULE.ensure_author_directory(library, "../../")
            self.assertEqual(author_dir.name, "未知博主")
            self.assertEqual(author_dir.parent, library.resolve())

    def test_default_library_is_on_desktop(self) -> None:
        with mock.patch.dict(MODULE.os.environ, {}, clear=True):
            expected = Path.home() / "Desktop" / "抖音无水印视频"
            self.assertEqual(Path(MODULE.default_output_dir()), expected)

    def test_output_environment_override_is_preserved(self) -> None:
        with mock.patch.dict(MODULE.os.environ, {"AH_DOUYIN_OUTPUT_DIR": "/tmp/custom-library"}, clear=True):
            self.assertEqual(MODULE.default_output_dir(), "/tmp/custom-library")

    def test_images_only_are_rejected(self) -> None:
        payload = {
            "aweme_list": [
                {
                    "aweme_id": "7123456789012345678",
                    "images": [{"url_list": ["https://example.test/image.jpg"]}],
                }
            ]
        }
        with self.assertRaises(MODULE.DownloadError):
            MODULE.parse_metadata(payload, "7123456789012345678")


if __name__ == "__main__":
    unittest.main()
