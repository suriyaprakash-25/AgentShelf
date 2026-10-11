"""External API/database probe; standard library only, no secrets or response-body logs."""

import argparse
import json
import math
import os
import time
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_BODY = 8192


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def target_url(origin, allow_loopback=False):
    """Accept an origin, never credentials, a path, query or fragment."""
    if not isinstance(origin, str) or not origin or len(origin) > 2048:
        raise ValueError("TARGET_INVALID")
    if any(character.isspace() or ord(character) < 32 for character in origin):
        raise ValueError("TARGET_INVALID")
    parsed = urlsplit(origin)
    local = allow_loopback and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if (
        not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or (not local and (parsed.scheme != "https" or parsed.port not in {None, 443}))
        or (local and parsed.scheme not in {"http", "https"})
    ):
        raise ValueError("TARGET_INVALID")
    return origin.rstrip("/") + "/healthz"


def probe(origin, expected_mode="sandbox", *, allow_loopback=False, timeout=10):
    """Return fixed-code evidence; a 200 response alone never establishes health."""
    started = time.monotonic()
    result = {"check": "api_database_uptime", "status": "failed"}
    try:
        if expected_mode not in {"sandbox", "live"}:
            raise ValueError("EXPECTED_MODE_INVALID")
        if (
            not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or not 1 <= timeout <= 30
        ):
            raise ValueError("TIMEOUT_INVALID")
        if not origin:
            raise ValueError("TARGET_NOT_CONFIGURED")
        url = target_url(origin, allow_loopback)
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "Cache-Control": "no-cache",
                "User-Agent": "AgentShelf-Uptime/1",
            },
        )
        with build_opener(NoRedirect()).open(request, timeout=timeout) as response:
            result["http_status"] = response.status
            body = response.read(MAX_BODY + 1)
            if response.status != 200:
                result["code"] = "HTTP_FAILURE"
            elif len(body) > MAX_BODY:
                result["code"] = "RESPONSE_TOO_LARGE"
            else:
                try:
                    data = json.loads(body)
                except (ValueError, UnicodeError, RecursionError):
                    data = None
                if (
                    not isinstance(data, dict)
                    or data.get("status") != "ok"
                    or data.get("database") != "reachable"
                    or data.get("paypal_mode") != expected_mode
                ):
                    result["code"] = "HEALTH_CONTRACT_FAILED"
                else:
                    result.update(status="passed", code="HEALTHY", paypal_mode=expected_mode)
    except HTTPError as exc:
        result.update(code="HTTP_FAILURE", http_status=exc.code)
        exc.close()
    except (URLError, TimeoutError, OSError, HTTPException):
        result["code"] = "NETWORK_FAILURE"
    except ValueError as exc:
        # Parsing errors may contain the invalid input. Never emit str(exc).
        codes = {"TARGET_NOT_CONFIGURED", "EXPECTED_MODE_INVALID", "TIMEOUT_INVALID"}
        result["code"] = str(exc) if str(exc) in codes else "TARGET_INVALID"
    result["duration_ms"] = round((time.monotonic() - started) * 1000)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", default=os.environ.get("STAGING_ORIGIN"))
    parser.add_argument("--expected-mode", choices=["sandbox", "live"], default="sandbox")
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument("--allow-loopback", action="store_true", help="Local verification only")
    args = parser.parse_args()
    result = probe(
        args.origin,
        args.expected_mode,
        timeout=args.timeout,
        allow_loopback=args.allow_loopback,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
