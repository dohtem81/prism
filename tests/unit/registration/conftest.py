import pytest

from services.registration.app.api import register as register_module


@pytest.fixture(autouse=True)
def no_registration_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(register_module, "enforce_registration_limits", lambda request, cache, email: None)


@pytest.fixture(autouse=True)
def sent_emails(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, str]]:
    sent: list[tuple[str, str, str]] = []
    monkeypatch.setattr(register_module, "send_verification_email", lambda *args: sent.append(args))
    return sent
