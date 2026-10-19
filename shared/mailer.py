import smtplib
from email.message import EmailMessage

from pydantic_settings import BaseSettings, SettingsConfigDict


class SmtpSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SMTP_", env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Defaults target the local Mailpit container (deploy/compose/docker-compose.yml).
    host: str = "mailpit"
    port: int = 1025
    username: str = ""
    password: str = ""
    starttls: bool = False
    sender: str = "Prism <no-reply@prism.local>"
    timeout_seconds: float = 10.0


def send_email(to: str, subject: str, body: str, *, smtp: SmtpSettings | None = None) -> None:
    cfg = smtp or SmtpSettings()
    message = EmailMessage()
    message["From"] = cfg.sender
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    with smtplib.SMTP(cfg.host, cfg.port, timeout=cfg.timeout_seconds) as client:
        if cfg.starttls:
            client.starttls()
        if cfg.username:
            client.login(cfg.username, cfg.password)
        client.send_message(message)
