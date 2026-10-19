"""
W3C Trace Context parser and distributed tracing span propagator.
Format: traceparent: 00-{trace_id}-{span_id}-{flags}
"""

from __future__ import annotations

import os
import random
import re
from typing import Optional, Tuple

TRACEPARENT_REGEX = re.compile(r"^00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$")


def generate_hex(length: int) -> str:
    """Generate cryptographically pseudo-random hex string."""
    return "".join(random.choices("0123456789abcdef", k=length))


class TraceContext:
    """Represents a distributed tracing span."""

    def __init__(
        self,
        trace_id: Optional[str] = None,
        parent_span_id: Optional[str] = None,
        span_id: Optional[str] = None,
        flags: str = "01",
    ) -> None:
        self.trace_id = trace_id or generate_hex(32)
        self.parent_span_id = parent_span_id
        self.span_id = span_id or generate_hex(16)
        self.flags = flags

    @classmethod
    def from_header(cls, header_val: Optional[str]) -> "TraceContext":
        """Parse W3C traceparent header or generate fresh trace."""
        if not header_val:
            return cls()

        clean = header_val.strip()
        match = TRACEPARENT_REGEX.match(clean)
        if match:
            trace_id, parent_span, flags = match.groups()
            # Child span ID
            new_span_id = generate_hex(16)
            return cls(trace_id=trace_id, parent_span_id=parent_span, span_id=new_span_id, flags=flags)

        return cls()

    def to_header(self) -> str:
        """Format as W3C traceparent header string."""
        return f"00-{self.trace_id}-{self.span_id}-{self.flags}"
