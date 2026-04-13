"""PII-safe helpers for logs and Langfuse trace payloads.

Free-text fields (user questions, rewritten queries, retrieved context,
model answers) can contain personal data and must not hit stdout or the
Langfuse store verbatim. These helpers replace the text with a short
sha256 prefix + length so operators can still group identical requests
and spot empty/oversized inputs without ever seeing the content.
"""

from __future__ import annotations

import hashlib
from typing import Any

REDACTED_MARKER = "<redacted>"


def hash_text(text: str | None) -> str:
    """Return `sha256:<12 hex>:len=<n>` for a free-text log field.

    Suitable for INFO-level logs — deterministic enough to correlate
    repeat requests, opaque enough to leak nothing.
    """
    if text is None:
        return "none"
    digest = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:12]
    return f"sha256:{digest}:len={len(text)}"


def mask_payload(*, data: Any, **_: Any) -> Any:
    """Langfuse `mask` hook — nuke all observation input/output.

    Applied globally on the Langfuse client so the LangChain
    CallbackHandler (which auto-publishes node state) cannot leak
    question / context / answer strings into traces. Usage details,
    model names, and span shape are untouched — only the `input` and
    `output` blobs flow through here.
    """
    return REDACTED_MARKER
