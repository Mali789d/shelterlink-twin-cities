"""Carrier-required SMS keywords: opt-out, opt-in, and help.

US carriers and Twilio's messaging policy expect every SMS program to honor STOP-style
opt-outs, resume on START, and answer HELP with program information. A person who texts
STOP must not get any further replies from us until they opt back in.

Phone numbers are never stored in plain text. The store keeps a salted SHA-256 digest so
an opt-out list cannot be read back as a list of people who used a homeless-services line.
"""

from __future__ import annotations

import hashlib
import os
import re
from enum import Enum
from typing import Protocol

from .i18n import Language

OPT_OUT_WORDS = {
    "stop", "stopall", "unsubscribe", "cancel", "end", "quit", "revoke", "optout",
    "parar", "jooji",
}
OPT_IN_WORDS = {"start", "unstop", "yes"}
HELP_WORDS = {
    "help": Language.ENGLISH,
    "info": Language.ENGLISH,
    "ayuda": Language.SPANISH,
    "caawimo": Language.SOMALI,
}


class Keyword(str, Enum):
    OPT_OUT = "opt_out"
    OPT_IN = "opt_in"
    HELP = "help"


def classify_keyword(body: str) -> tuple[Keyword, Language] | None:
    """Match only when the whole message is a keyword, so '55415 end of block' still searches."""
    word = re.sub(r"[^\w-]", "", body.strip().lower().replace(" ", ""))
    if word in OPT_OUT_WORDS:
        return Keyword.OPT_OUT, Language.ENGLISH
    if word in OPT_IN_WORDS:
        return Keyword.OPT_IN, Language.ENGLISH
    if word in HELP_WORDS:
        return Keyword.HELP, HELP_WORDS[word]
    return None


def hash_phone(phone: str, salt: str) -> str:
    normalized = re.sub(r"[^\d+]", "", phone)
    return hashlib.sha256(f"{salt}:{normalized}".encode("utf-8")).hexdigest()


class OptOutStore(Protocol):
    def is_opted_out(self, phone: str) -> bool: ...
    def opt_out(self, phone: str) -> None: ...
    def opt_in(self, phone: str) -> None: ...


class InMemoryOptOutStore:
    """Process-local store for development and tests.

    Not durable: a restart or a new serverless instance forgets opt-outs. Production must
    use a persistent store before launch (tracked on the roadmap). Twilio's own opt-out
    handling still blocks delivery to opted-out numbers in the meantime.
    """

    def __init__(self, salt: str | None = None) -> None:
        self._salt = salt if salt is not None else os.environ.get("OPT_OUT_HASH_SALT", "dev-salt")
        self._opted_out: set[str] = set()

    def is_opted_out(self, phone: str) -> bool:
        return bool(phone) and hash_phone(phone, self._salt) in self._opted_out

    def opt_out(self, phone: str) -> None:
        if phone:
            self._opted_out.add(hash_phone(phone, self._salt))

    def opt_in(self, phone: str) -> None:
        self._opted_out.discard(hash_phone(phone, self._salt))

    def stored_digests(self) -> frozenset[str]:
        return frozenset(self._opted_out)
