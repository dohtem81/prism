import pytest

from services.api.app.auth import login_guard
from tests.support.fake_redis import FakeRedis


@pytest.fixture(autouse=True)
def isolated_login_guard(monkeypatch: pytest.MonkeyPatch) -> FakeRedis:
    fake = FakeRedis()
    monkeypatch.setattr(login_guard, "get_client", lambda: fake)
    return fake
