from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any, Callable, Dict, Optional

import requests

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_TIMEOUT = 3.0
DEFAULT_RETRIES = 15
DEFAULT_DELAY = 1.0

SAMPLE_INGEST_PAYLOAD: Dict[str, Any] = {
    "timestamp": "2025-01-01T00:00:00Z",
    "sensor_id": "ci-smoke",
    "modality": "rf",
    "location": {"lat": 42.0, "lon": -71.0},
    "data": {"type": "rf_detection", "value": {"frequency_hz": 915_000_000}},
    "source_format": "zmeta",
    "schema_version": "1.0",
}


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe key endpoints in the running FastAPI application.",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Service base URL (default: {DEFAULT_BASE_URL}).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"Per-request timeout in seconds (default: {DEFAULT_TIMEOUT}).",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=DEFAULT_RETRIES,
        help="Number of retry attempts before failing (default: 15).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY,
        help="Delay between retries in seconds (default: 1).",
    )
    parser.add_argument(
        "--shared-secret",
        default="",
        help="Optional shared secret sent via the x-zmeta-secret header for ingest checks.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Log retry attempts to stderr.",
    )
    return parser.parse_args(argv)


def build_url(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + "/" + path.lstrip("/")


def ensure_html_response(response: requests.Response) -> None:
    content_type = response.headers.get("content-type", "").lower()
    if "text/html" not in content_type:
        raise AssertionError(f"Unexpected content-type: {content_type}")
    body = response.text.strip().lower()
    if "<html" not in body:
        raise AssertionError("Response body does not look like HTML")


def ensure_ingest_response(response: requests.Response) -> None:
    try:
        payload = response.json()
    except json.JSONDecodeError as exc:
        raise AssertionError("Ingest endpoint did not return JSON") from exc

    if not isinstance(payload, dict):
        raise AssertionError("Ingest response was not a JSON object")

    if payload.get("ok") is not True:
        raise AssertionError(f"Unexpected ingest response: {payload}")

    if "broadcast_to" not in payload:
        raise AssertionError("Ingest response missing broadcast_to field")


Validator = Callable[[requests.Response], None]

CHECKS: list[dict[str, Any]] = [
    {
        "name": "docs-local",
        "path": "/docs/local",
        "method": "GET",
        "expect_status": 200,
        "validator": ensure_html_response,
    },
    {
        "name": "docs-pipeline",
        "path": "/docs/pipeline",
        "method": "GET",
        "expect_status": 200,
        "validator": ensure_html_response,
    },
    {
        "name": "ingest",
        "path": "/api/v1/ingest",
        "method": "POST",
        "expect_status": 200,
        "json": SAMPLE_INGEST_PAYLOAD,
        "validator": ensure_ingest_response,
    },
]


def run_check(
    session: requests.Session,
    *,
    base_url: str,
    spec: dict[str, Any],
    timeout: float,
    retries: int,
    delay: float,
    shared_secret: str,
    verbose: bool,
) -> None:
    url = build_url(base_url, spec["path"])
    method = spec["method"].upper()
    expect_status = spec.get("expect_status", 200)
    json_payload = spec.get("json")
    validator: Optional[Validator] = spec.get("validator")

    headers: dict[str, str] = {}
    if spec["name"] == "ingest" and shared_secret:
        headers["x-zmeta-secret"] = shared_secret

    last_error: Optional[BaseException] = None

    for attempt in range(1, retries + 1):
        try:
            response = session.request(
                method,
                url,
                timeout=timeout,
                json=json_payload,
                headers=headers,
            )
            if response.status_code != expect_status:
                raise AssertionError(
                    f"Expected HTTP {expect_status} but received {response.status_code}: {response.text[:200]}"
                )
            if validator is not None:
                validator(response)
            if verbose:
                print(f"[ok] {spec['name']} ({method} {url})", file=sys.stderr)
            return
        except (requests.RequestException, AssertionError) as exc:
            last_error = exc
            if verbose:
                print(
                    f"Attempt {attempt}/{retries} for {spec['name']} failed: {exc}",
                    file=sys.stderr,
                )
            if attempt < retries:
                time.sleep(delay)

    assert last_error is not None
    raise RuntimeError(f"check '{spec['name']}' failed after {retries} attempts") from last_error


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)

    with requests.Session() as session:
        for spec in CHECKS:
            run_check(
                session,
                base_url=args.base_url,
                spec=spec,
                timeout=args.timeout,
                retries=args.retries,
                delay=args.delay,
                shared_secret=args.shared_secret,
                verbose=args.verbose,
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
