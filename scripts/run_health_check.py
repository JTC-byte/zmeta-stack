"""CLI utility to query the FastAPI health endpoint."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict

import requests

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_ENDPOINT = "/api/v1/healthz"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Call the FastAPI health endpoint and report the result.",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Server base URL (default: {DEFAULT_BASE_URL}).",
    )
    parser.add_argument(
        "--endpoint",
        default=DEFAULT_ENDPOINT,
        help=f"Health endpoint path (default: {DEFAULT_ENDPOINT}).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="Request timeout in seconds (default: 5).",
    )
    parser.add_argument(
        "--output",
        choices=("pretty", "json", "status"),
        default="pretty",
        help="Output format: pretty, json, or status only.",
    )
    parser.add_argument(
        "--expected-status",
        default="ok",
        help="Value expected in the response's `status` field (default: ok).",
    )
    parser.add_argument(
        "--skip-status-check",
        action="store_true",
        help="Do not fail the command when the status field does not match.",
    )
    return parser.parse_args(argv)


def build_url(base_url: str, endpoint: str) -> str:
    return base_url.rstrip("/") + "/" + endpoint.lstrip("/")


def fetch_health(url: str, timeout: float) -> Dict[str, Any]:
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return response.json()


def format_output(data: Dict[str, Any], mode: str) -> str:
    if mode == "json":
        return json.dumps(data)
    if mode == "status":
        return str(data.get("status"))
    return json.dumps(data, indent=2, sort_keys=True)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    url = build_url(args.base_url, args.endpoint)

    try:
        payload = fetch_health(url, timeout=args.timeout)
    except requests.RequestException as exc:
        print(f"Health check request failed: {exc}", file=sys.stderr)
        return 2

    if not args.skip_status_check:
        expected_status = args.expected_status
        actual_status = payload.get("status")
        if actual_status != expected_status:
            print(
                f"Unexpected status value: expected '{expected_status}', got '{actual_status}'",
                file=sys.stderr,
            )
            print(json.dumps(payload, indent=2, sort_keys=True), file=sys.stderr)
            return 3

    print(format_output(payload, args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
