"""Transactional email (SMTP) with a mock-send fallback.

When ``settings.smtp_enabled`` is false (the default), emails are NOT sent over
the network — they're logged so the ticketing feature works end-to-end before
real SMTP credentials are configured. ``send_email`` is synchronous; callers run
it off the event loop (``asyncio.to_thread`` / fire-and-forget)."""

from __future__ import annotations

from email.message import EmailMessage
import logging
import smtplib

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def send_email(to: str, subject: str, body_text: str, body_html: str | None = None) -> bool:
    """Send (or mock-log) an email. Returns True on success/mock, False on error.
    Never raises — email is best-effort and must not break the calling flow."""
    if not settings.smtp_enabled:
        logger.info(
            "EMAIL (mock, not sent) to=%s subject=%r\n%s",
            to,
            subject,
            body_text,
        )
        return True

    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body_text)
    if body_html:
        msg.add_alternative(body_html, subtype="html")

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
        logger.info("Email sent to=%s subject=%r", to, subject)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Email send failed to=%s subject=%r: %s", to, subject, exc)
        return False


# --- Templates (bilingual: Arabic + English) -------------------------------

def otp_email(code: str, ttl_minutes: int) -> tuple[str, str]:
    subject = "رمز التحقق - GoBus | Your verification code"
    body = (
        f"رمز التحقق الخاص بك هو: {code}\n"
        f"صالح لمدة {ttl_minutes} دقائق. لا تشاركه مع أحد.\n\n"
        f"Your GoBus verification code is: {code}\n"
        f"It is valid for {ttl_minutes} minutes. Do not share it with anyone."
    )
    return subject, body


_CATEGORY_LABELS = {
    "en": {
        "booking": "Booking",
        "refund_payment": "Refund / Payment",
        "complaint": "Complaint",
        "lost_item": "Lost item",
        "schedule_trip": "Schedule / Trip",
        "other": "Other",
    },
    "ar": {
        "booking": "الحجز",
        "refund_payment": "استرداد / دفع",
        "complaint": "شكوى",
        "lost_item": "مفقودات",
        "schedule_trip": "مواعيد / رحلة",
        "other": "أخرى",
    },
}


def _category_label(category: str, lang: str) -> str:
    return _CATEGORY_LABELS.get(lang, _CATEGORY_LABELS["en"]).get(category, category)


def _rows_html(rows: list[tuple[str, str]], rtl: bool) -> str:
    align = "right" if rtl else "left"
    trs = "".join(
        f'<tr><td style="padding:8px 12px;border:1px solid #e5e7eb;background:#f9fafb;'
        f'font-weight:600;text-align:{align}">{k}</td>'
        f'<td style="padding:8px 12px;border:1px solid #e5e7eb;text-align:{align}">{v}</td></tr>'
        for k, v in rows
    )
    return (
        f'<table style="border-collapse:collapse;border:1px solid #e5e7eb;'
        f'font-family:Arial,Helvetica,sans-serif;font-size:14px;margin:12px 0">{trs}</table>'
    )


def _wrap_html(body_inner: str, rtl: bool) -> str:
    direction = "rtl" if rtl else "ltr"
    return (
        f'<div dir="{direction}" style="font-family:Arial,Helvetica,sans-serif;'
        f'font-size:14px;color:#111827;line-height:1.6;max-width:560px">{body_inner}</div>'
    )


def ticket_created_email(
    ref_number: str,
    subject_line: str,
    category: str,
    customer_name: str | None = None,
    hotline: str = "19567",
    lang: str = "en",
) -> tuple[str, str, str]:
    """Return (subject, text_body, html_body) for the ticket-created email."""
    name = (customer_name or "").strip()
    cat = _category_label(category, lang)
    if lang == "ar":
        subject = f"تم إنشاء تذكرتك {ref_number} - GoBus"
        greeting = f"عزيزي {name}،" if name else "عزيزي العميل،"
        rows = [("رقم التذكرة", ref_number), ("الموضوع", subject_line), ("التصنيف", cat)]
        text = (
            f"{greeting}\n\n"
            f"تم إنشاء تذكرتك بنجاح.\n\n"
            f"رقم التذكرة: {ref_number}\n"
            f"الموضوع: {subject_line}\n"
            f"التصنيف: {cat}\n\n"
            f"سيقوم فريق خدمة العملاء بمراجعة طلبك والتواصل معك في أقرب وقت ممكن.\n"
            f"للمساعدة أو المتابعة، يرجى الاتصال بالخط الساخن: {hotline}.\n\n"
            f"مع خالص التحية،\nفريق خدمة العملاء"
        )
        html = _wrap_html(
            f"<p>{greeting}</p><p>تم إنشاء تذكرتك بنجاح.</p>{_rows_html(rows, True)}"
            f"<p>سيقوم فريق خدمة العملاء بمراجعة طلبك والتواصل معك في أقرب وقت ممكن.</p>"
            f"<p>للمساعدة أو المتابعة، يرجى الاتصال بالخط الساخن: <strong>{hotline}</strong>.</p>"
            f"<p>مع خالص التحية،<br/>فريق خدمة العملاء</p>",
            True,
        )
        return subject, text, html

    subject = f"Ticket {ref_number} created - GoBus Support"
    greeting = f"Dear {name}," if name else "Dear Customer,"
    rows = [("Ticket Number", ref_number), ("Subject", subject_line), ("Category", cat)]
    text = (
        f"{greeting}\n\n"
        f"Your support ticket has been created successfully.\n\n"
        f"Ticket Number: {ref_number}\n"
        f"Subject: {subject_line}\n"
        f"Category: {cat}\n\n"
        f"Our Customer Support team will review your request and follow up with you as soon as possible.\n"
        f"For further assistance, please contact our hotline: {hotline}.\n\n"
        f"Best regards,\nCustomer Support Team"
    )
    html = _wrap_html(
        f"<p>{greeting}</p><p>Your support ticket has been created successfully.</p>{_rows_html(rows, False)}"
        f"<p>Our Customer Support team will review your request and follow up with you as soon as possible.</p>"
        f"<p>For further assistance, please contact our hotline: <strong>{hotline}</strong>.</p>"
        f"<p>Best regards,<br/>Customer Support Team</p>",
        False,
    )
    return subject, text, html


def ticket_resolved_email(
    ref_number: str,
    subject_line: str,
    customer_name: str | None = None,
    hotline: str = "19567",
    lang: str = "en",
) -> tuple[str, str, str]:
    """Return (subject, text_body, html_body) for the ticket-resolved email."""
    name = (customer_name or "").strip()
    if lang == "ar":
        subject = f"تم حل تذكرتك {ref_number} - GoBus"
        greeting = f"عزيزي {name}،" if name else "عزيزي العميل،"
        rows = [("رقم التذكرة", ref_number), ("الموضوع", subject_line), ("الحالة", "تم الحل")]
        text = (
            f"{greeting}\n\n"
            f"يسعدنا إبلاغك بأنه تم حل تذكرتك.\n\n"
            f"رقم التذكرة: {ref_number}\n"
            f"الموضوع: {subject_line}\n"
            f"الحالة: تم الحل\n\n"
            f"إذا كنت بحاجة لمزيد من المساعدة، يرجى الاتصال بالخط الساخن: {hotline}.\n\n"
            f"مع خالص التحية،\nفريق خدمة العملاء"
        )
        html = _wrap_html(
            f"<p>{greeting}</p><p>يسعدنا إبلاغك بأنه تم حل تذكرتك.</p>{_rows_html(rows, True)}"
            f"<p>إذا كنت بحاجة لمزيد من المساعدة، يرجى الاتصال بالخط الساخن: <strong>{hotline}</strong>.</p>"
            f"<p>مع خالص التحية،<br/>فريق خدمة العملاء</p>",
            True,
        )
        return subject, text, html

    subject = f"Ticket {ref_number} resolved - GoBus Support"
    greeting = f"Dear {name}," if name else "Dear Customer,"
    rows = [("Ticket Number", ref_number), ("Subject", subject_line), ("Status", "Resolved")]
    text = (
        f"{greeting}\n\n"
        f"We're glad to let you know that your support ticket has been resolved.\n\n"
        f"Ticket Number: {ref_number}\n"
        f"Subject: {subject_line}\n"
        f"Status: Resolved\n\n"
        f"If you need further assistance, please contact our hotline: {hotline}.\n\n"
        f"Best regards,\nCustomer Support Team"
    )
    html = _wrap_html(
        f"<p>{greeting}</p><p>We're glad to let you know that your support ticket has been resolved.</p>"
        f"{_rows_html(rows, False)}"
        f"<p>If you need further assistance, please contact our hotline: <strong>{hotline}</strong>.</p>"
        f"<p>Best regards,<br/>Customer Support Team</p>",
        False,
    )
    return subject, text, html
