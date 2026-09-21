from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SkillPackageTests(unittest.TestCase):
    def test_required_release_files_exist(self) -> None:
        required = (
            "README.md",
            "SKILL.md",
            "LICENSE",
            "PROVENANCE.md",
            "THIRD_PARTY_NOTICES.md",
            "SECURITY.md",
            "agents/openai.yaml",
            "scripts/download_douyin.py",
            "scripts/doctor.py",
        )
        missing = [name for name in required if not (ROOT / name).is_file()]
        self.assertEqual(missing, [])

    def test_skill_frontmatter_and_portability(self) -> None:
        text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"))
        self.assertIn("name: ah-douyin-clean-downloader", text)
        self.assertIn("description:", text)
        self.assertIn("${CODEX_HOME:-$HOME/.codex}", text)
        self.assertIn("用户只发送一条抖音官方链接", text)
        self.assertIn("抖音无水印视频/<博主昵称>", text)
        self.assertNotIn("/Users/", text)

    def test_no_real_media_or_partial_files_are_committed(self) -> None:
        forbidden = [
            path
            for path in ROOT.rglob("*")
            if path.is_file() and (path.suffix.lower() == ".mp4" or path.name.endswith(".part"))
        ]
        self.assertEqual(forbidden, [])


if __name__ == "__main__":
    unittest.main()
