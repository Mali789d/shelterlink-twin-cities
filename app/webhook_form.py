"""Bounded, unambiguous Twilio form parsing before signature or consent work."""
import re
from urllib.parse import parse_qsl

from fastapi import HTTPException, Request
from starlette.datastructures import FormData

MAX_BODY_BYTES = 16 * 1024
MAX_FIELDS = 64


async def read_sms_form(request: Request) -> FormData:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/x-www-form-urlencoded":
        raise HTTPException(status_code=415, detail="SMS requires a URL-encoded form")
    chunks = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            raise HTTPException(status_code=413, detail="SMS form is too large")
        chunks.append(chunk)
    try:
        text = b"".join(chunks).decode("utf-8")
        if re.search(r"%(?![0-9a-fA-F]{2})", text):
            raise ValueError("invalid percent escape")
        fields = parse_qsl(text, keep_blank_values=True, encoding="utf-8", errors="strict",
                           max_num_fields=MAX_FIELDS)
    except (UnicodeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid SMS form") from None
    form = FormData(fields)
    # Signing every value does not make choosing one duplicate value unambiguous.
    for key in ("Body", "From", "To", "MessageSid", "SmsSid", "AccountSid"):
        if len(form.getlist(key)) > 1:
            raise HTTPException(status_code=400, detail="Duplicate SMS field")
    return form
