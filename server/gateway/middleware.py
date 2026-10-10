"""API Gateway cross-cutting: request ID, demo tenancy, CORS helpers."""

from __future__ import annotations

import uuid
from typing import Optional

from flask import Request, g


DEMO_CUSTOMER = "cust_acme"


def bind_request_context(req: Request) -> None:
    g.request_id = req.headers.get("X-Request-Id") or str(uuid.uuid4())
    g.customer_id = req.headers.get("X-Customer-Id") or DEMO_CUSTOMER


def customer_id() -> str:
    return getattr(g, "customer_id", DEMO_CUSTOMER)


def request_id() -> Optional[str]:
    return getattr(g, "request_id", None)
