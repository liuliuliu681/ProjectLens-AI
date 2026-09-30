from pathlib import Path

from app import _parse_uploaded, _safe_error
from core.llm_client import LLMAuthenticationError, LLMRateLimitError, LLMServerError, LLMTimeoutError


class Upload:
    def __init__(self, path: Path):
        self.name = path.name
        self.content = path.read_bytes()
        self.size = len(self.content)

    def getvalue(self) -> bytes:
        return self.content


def test_uploaded_real_files_use_formal_parsers():
    fixtures = Path(__file__).parent / "fixtures"
    experiments = _parse_uploaded(Upload(fixtures / "real_experiments.json"), True)
    flutter = _parse_uploaded(Upload(fixtures / "flutter_test_real.log"), False)
    godot = _parse_uploaded(Upload(fixtures / "godot_test_real.log"), False)
    assert [run.name for run in experiments.experiments] == ["B0_rgb_baseline", "C1_rgbd_dual_p3p4"]
    assert flutter.test_summary.passed == 242
    assert flutter.test_summary.skipped == 15
    assert godot.test_summary.unit == "test_group"
    assert godot.test_summary.total == 51


def test_api_errors_are_presented_without_raw_details():
    assert "401" in _safe_error(LLMAuthenticationError("secret"))
    assert "429" in _safe_error(LLMRateLimitError("secret"))
    assert "超时" in _safe_error(LLMTimeoutError("secret"))
    assert "服务" in _safe_error(LLMServerError("secret"))
    assert "secret" not in _safe_error(LLMAuthenticationError("secret"))
