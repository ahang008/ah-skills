"""Run the response-boundary regression cases without writing user artifacts."""
import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_response.py"
SPEC = importlib.util.spec_from_file_location("response_checker", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

VALID = (
    "SCRIPT_BEGIN task_id=GSP-test revision=1\n这是一篇完整的口播稿。\n"
    "SCRIPT_END task_id=GSP-test revision=1\n修改说明: 未新增事实\n"
    "REPLY_DONE task_id=GSP-test revision=1"
)


class ResponseBoundaryTests(unittest.TestCase):
    def test_boundary_cases(self):
        cases = [
            ("valid", VALID, {}, True),
            ("truncated", VALID.rsplit("\n", 1)[0], {}, False),
            ("stale_task", VALID.replace("GSP-test", "GSP-old"), {}, False),
            ("wrong_revision", VALID.replace("revision=1", "revision=2"), {}, False),
            ("duplicate_response", VALID + "\n" + VALID, {}, False),
            ("empty_script", VALID.replace("这是一篇完整的口播稿。", ""), {}, False),
            ("too_short", VALID, {"min_chars": 100}, False),
            ("too_long", VALID, {"max_chars": 5}, False),
            ("missing_input", "NEEDS_INPUT task_id=GSP-test revision=1\n请补充事实\nREPLY_DONE task_id=GSP-test revision=1", {}, False),
            ("protocol_in_body", VALID.replace("这是一篇完整的口播稿。", "不要打印 REPLY_DONE"), {}, False),
            ("extra_after_done", VALID + "\n还有正文", {}, False),
            ("embedded_second_begin", VALID.replace("这是一篇完整的口播稿。", "这个分工逻辑其实SCRIPT_BEGIN task_id=GSP-test revision=1\n第二个稿件"), {}, False),
        ]
        for name, text, limits, should_pass in cases:
            with self.subTest(case=name):
                if should_pass:
                    body, count = MODULE.extract_script(text, "GSP-test", 1, **limits)
                    self.assertEqual(body, "这是一篇完整的口播稿。")
                    self.assertEqual(count, len(body))
                else:
                    with self.assertRaises(ValueError):
                        MODULE.extract_script(text, "GSP-test", 1, **limits)


if __name__ == "__main__":
    unittest.main(verbosity=2)
