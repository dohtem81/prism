from unittest.mock import MagicMock, patch

from shared.mailer import SmtpSettings, send_email


def test_send_email_uses_local_smtp_without_auth() -> None:
    client = MagicMock()
    with patch("shared.mailer.smtplib.SMTP") as smtp_cls:
        smtp_cls.return_value.__enter__.return_value = client
        send_email("a@example.com", "Hi", "Body", smtp=SmtpSettings(host="mailpit", port=1025))

    smtp_cls.assert_called_once_with("mailpit", 1025, timeout=10.0)
    client.starttls.assert_not_called()
    client.login.assert_not_called()
    sent = client.send_message.call_args.args[0]
    assert sent["To"] == "a@example.com"
    assert sent["Subject"] == "Hi"


def test_send_email_uses_starttls_and_login_when_configured() -> None:
    client = MagicMock()
    cfg = SmtpSettings(host="smtp.example.com", port=587, username="u", password="p", starttls=True)
    with patch("shared.mailer.smtplib.SMTP") as smtp_cls:
        smtp_cls.return_value.__enter__.return_value = client
        send_email("a@example.com", "Hi", "Body", smtp=cfg)

    client.starttls.assert_called_once()
    client.login.assert_called_once_with("u", "p")
