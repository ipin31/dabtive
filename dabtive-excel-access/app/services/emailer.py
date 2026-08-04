from email.message import EmailMessage
import smtplib
from app.config import get_settings

settings = get_settings()


def send_email(to_email: str, subject: str, text: str, html: str | None = None) -> None:
    if not settings.smtp_enabled:
        print(f"[EMAIL DISABLED] To={to_email} Subject={subject}\n{text}")
        return
    msg = EmailMessage()
    msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(msg)
