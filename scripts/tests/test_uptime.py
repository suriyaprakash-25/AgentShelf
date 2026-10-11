"""Probe behavior against an actual loopback HTTP server, never a provider claim."""

import importlib.util
import json
import subprocess
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "check-uptime.py"
spec = importlib.util.spec_from_file_location("uptime", SCRIPT)
uptime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(uptime)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.server.paths.append(self.path)
        time.sleep(self.server.delay)
        status, body, headers = self.server.reply
        self.send_response(status)
        for name, value in headers.items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            pass

    def log_message(self, *_args):
        pass


class UptimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.origin = f"http://127.0.0.1:{cls.server.server_port}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def setUp(self):
        self.server.paths = []
        self.server.delay = 0
        self.reply({"status": "ok", "database": "reachable", "paypal_mode": "sandbox"})

    def reply(self, body, status=200, headers=None):
        if not isinstance(body, bytes):
            body = json.dumps(body).encode()
        self.server.reply = (status, body, headers or {})

    def check(self):
        return uptime.probe(self.origin, allow_loopback=True)

    def test_valid_api_and_database(self):
        result = self.check()
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["paypal_mode"], "sandbox")
        self.assertEqual(self.server.paths, ["/healthz"])

    def test_http_requires_explicit_loopback_flag(self):
        self.assertEqual(uptime.probe(self.origin)["code"], "TARGET_INVALID")
        self.assertEqual(self.server.paths, [])

    def test_origin_rejects_credentials_path_query_and_fragment(self):
        for origin in [
            "https://user:private-password@example.test",
            "https://example.test/path",
            "https://example.test?private-token=value",
            "https://example.test#private-token",
            "https://example.test:444",
            "https://example.test\n",
            "https://[broken",
        ]:
            with self.subTest(origin=origin):
                result = uptime.probe(origin)
                self.assertEqual(result["code"], "TARGET_INVALID")
                self.assertNotIn("private", json.dumps(result))

    def test_unconfigured_target_does_not_pass(self):
        self.assertEqual(uptime.probe(None)["code"], "TARGET_NOT_CONFIGURED")

    def test_database_failure_even_with_http_200(self):
        self.reply({"status": "ok", "database": "unreachable", "paypal_mode": "sandbox"})
        self.assertEqual(self.check()["code"], "HEALTH_CONTRACT_FAILED")

    def test_live_endpoint_cannot_pass_sandbox_monitor(self):
        self.reply({"status": "ok", "database": "reachable", "paypal_mode": "live"})
        self.assertEqual(self.check()["code"], "HEALTH_CONTRACT_FAILED")

    def test_non_json_body_is_not_logged(self):
        self.reply(b"private-email@example.test private-provider-body")
        result = self.check()
        self.assertEqual(result["code"], "HEALTH_CONTRACT_FAILED")
        self.assertNotIn("private", json.dumps(result))

    def test_http_error_is_not_logged(self):
        self.reply(b"private-provider-body", status=503)
        result = self.check()
        self.assertEqual(result["code"], "HTTP_FAILURE")
        self.assertEqual(result["http_status"], 503)
        self.assertNotIn("private", json.dumps(result))

    def test_redirect_is_not_followed(self):
        self.reply(b"", status=302, headers={"Location": self.origin + "/private"})
        self.assertEqual(self.check()["code"], "HTTP_FAILURE")
        self.assertEqual(self.server.paths, ["/healthz"])

    def test_oversized_body_is_rejected(self):
        self.reply(b"x" * (uptime.MAX_BODY + 1))
        self.assertEqual(self.check()["code"], "RESPONSE_TOO_LARGE")

    def test_timeout_is_bounded(self):
        for value in [0, 31, float("nan"), float("inf")]:
            with self.subTest(value=value):
                self.assertEqual(
                    uptime.probe(self.origin, timeout=value)["code"], "TIMEOUT_INVALID"
                )
        self.assertEqual(self.server.paths, [])

    def test_slow_server_times_out_without_exception_text(self):
        self.server.delay = 1.2
        started = time.monotonic()
        result = uptime.probe(self.origin, allow_loopback=True, timeout=1)
        self.assertEqual(result["code"], "NETWORK_FAILURE")
        self.assertLess(time.monotonic() - started, 2)

    def test_live_requires_explicit_expected_mode(self):
        self.reply({"status": "ok", "database": "reachable", "paypal_mode": "live"})
        result = uptime.probe(self.origin, expected_mode="live", allow_loopback=True)
        self.assertEqual(result["status"], "passed")

    def test_cli_returns_failure_for_unhealthy_response(self):
        self.reply({"status": "unavailable", "database": "unreachable", "private": "secret"})
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--origin", self.origin, "--allow-loopback"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["code"], "HEALTH_CONTRACT_FAILED")
        self.assertNotIn("secret", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
