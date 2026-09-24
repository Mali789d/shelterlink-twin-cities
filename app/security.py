"""Twilio webhook request-signature validation.

Twilio signs every webhook with ``X-Twilio-Signature``: the Base64 HMAC-SHA1 of the
full public URL followed by each POST parameter name and value, sorted by name, keyed
with the account auth token. Verifying it keeps anyone who discovers the webhook URL
from spoofing SMS traffic or running up message costs.

Configuration (environment variables):

- ``TWILIO_AUTH_TOKEN``: when set, every ``/sms`` request must carry a valid signature.
- ``PUBLIC_BASE_URL``: the externally visible origin (for example the API Gateway URL).
  Behind a proxy the app sees an internal URL, so Twilio's signature would never match
  without this.
- ``SHELTERLINK_ENV``: set to ``production`` to refuse unsigned traffic when no token is
  configured, so a missing secret fails closed instead of silently disabling the check.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlsplit, urlunsplit


def compute_signature(auth_token: str, url: str, params: Mapping[str, str | Iterable[str]]) -> str:
    """Return the signature Twilio would send for ``url`` and form ``params``."""
    payload = url
    for key in sorted(params):
        value = params[key]
        values = [value] if isinstance(value, str) else sorted(value)
        for item in values:
            payload += key + item
    digest = hmac.new(auth_token.encode("utf-8"), payload.encode("utf-8"), hashlib.sha1).digest()
    return base64.b64encode(digest).decode("ascii")


def _url_variants(url: str) -> list[str]:
    """Twilio may sign with or without an explicit default port; accept both forms."""
    parts = urlsplit(url)
    variants = [url]
    default_port = {"https": 443, "http": 80}.get(parts.scheme)
    host = parts.hostname or ""
    if parts.port is None and default_port:
        variants.append(urlunsplit(parts._replace(netloc=f"{host}:{default_port}")))
    elif parts.port == default_port:
        variants.append(urlunsplit(parts._replace(netloc=host)))
    return variants


def is_valid_signature(
    auth_token: str,
    url: str,
    params: Mapping[str, str | Iterable[str]],
    signature: str | None,
) -> bool:
    if not signature:
        return False
    return any(
        hmac.compare_digest(compute_signature(auth_token, candidate, params), signature)
        for candidate in _url_variants(url)
    )


class Verdict(str, Enum):
    ACCEPT = "accept"
    REJECT = "reject"
    MISCONFIGURED = "misconfigured"


@dataclass(frozen=True)
class WebhookSecurity:
    auth_token: str | None
    public_base_url: str | None
    production: bool

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "WebhookSecurity":
        env = os.environ if env is None else env
        return cls(
            auth_token=env.get("TWILIO_AUTH_TOKEN") or None,
            public_base_url=(env.get("PUBLIC_BASE_URL") or "").rstrip("/") or None,
            production=env.get("SHELTERLINK_ENV", "").lower() == "production",
        )

    def signed_url(self, request_url: str) -> str:
        """Rebuild the URL Twilio signed, swapping in the public origin when configured."""
        if not self.public_base_url:
            return request_url
        parts = urlsplit(request_url)
        path = parts.path + (f"?{parts.query}" if parts.query else "")
        return self.public_base_url.rstrip("/") + path

    def check(
        self,
        request_url: str,
        params: Mapping[str, str | Iterable[str]],
        signature: str | None,
    ) -> Verdict:
        if not self.auth_token:
            return Verdict.MISCONFIGURED if self.production else Verdict.ACCEPT
        if is_valid_signature(self.auth_token, self.signed_url(request_url), params, signature):
            return Verdict.ACCEPT
        return Verdict.REJECT
