import subprocess
import sys


def test_third_party_logs_include_correlation_id() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import logging; "
                "from shared.logging_utils import get_logger; "
                "get_logger('prism.test'); "
                "logging.getLogger('httpx').info('local request')"
            ),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "correlation_id=n/a local request" in result.stderr
    assert "Logging error" not in result.stderr
