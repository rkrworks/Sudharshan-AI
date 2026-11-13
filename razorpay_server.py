#!/usr/bin/env python3
import base64
import contextlib
import datetime
import hashlib
import hmac
import http.server
import json
import os
import secrets
import socketserver
import sqlite3
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, Generator, Optional, Tuple

from bajrang_core import (
    RSA_2048_MODULUS,
    RSA_2048_PRIME_P,
    RSA_2048_PRIME_Q,
    RSA_PUBLIC_EXPONENT,
    LicenseManager,
)

RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "rzp_test_BajrangArgonV6")
RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "")
RAZORPAY_WEBHOOK_SECRET = os.environ.get("RAZORPAY_WEBHOOK_SECRET", "")

ADMIN_PASSKEY_SHA256 = os.environ.get(
    "BAJRANG_ADMIN_TOKEN_SHA256",
    hashlib.sha256(b"bajrang-server-admin-secret-change-in-env").hexdigest(),
)


def _compute_rsa_2048_private_exponent() -> int:
    env_d = os.environ.get("BAJRANG_RSA_PRIVATE_D_HEX", "").strip()
    if env_d:
        return int(env_d, 16)
    phi = (RSA_2048_PRIME_P - 1) * (RSA_2048_PRIME_Q - 1)
    return pow(RSA_PUBLIC_EXPONENT, -1, phi)


RSA_2048_PRIVATE_EXPONENT = _compute_rsa_2048_private_exponent()


class AsymmetricLicenseIssuer:
    @staticmethod
    def issue_license_certificate(
        email: str,
        order_id: str,
        payment_id: str,
        plan: str = "PRO_99_INR",
        days_valid: int = 365,
    ) -> str:
        exp_ts = (datetime.date.today() + datetime.timedelta(days=days_valid)).isoformat()
        payload = {
            "sub": email.strip().lower(),
            "order_id": order_id,
            "payment_id": payment_id,
            "plan": plan,
            "iat": int(time.time()),
            "exp": exp_ts,
            "alg": "RSA-2048-SHA256",
        }
        payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode("ascii").rstrip("=")
        digest_int = int.from_bytes(hashlib.sha256(payload_bytes).digest(), "big")
        sig_int = pow(digest_int, RSA_2048_PRIVATE_EXPONENT, RSA_2048_MODULUS)
        sig_hex = format(sig_int, "x")
        return f"BAJRANG-V6-{payload_b64}.{sig_hex}"

    @staticmethod
    def verify_certificate(cert: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        with tempfile.TemporaryDirectory() as tmp:
            mgr = LicenseManager(Path(tmp))
            ok, _ = mgr.verify_key(cert)
            if not ok:
                return False, None
            body = cert.strip()[len("BAJRANG-V6-") :]
            payload_b64, _ = body.split(".", 1)
            pad = "=" * ((4 - len(payload_b64) % 4) % 4)
            payload = json.loads(base64.urlsafe_b64decode(payload_b64 + pad).decode("utf-8"))
            return True, payload


class RazorpayFulfillmentEngine:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or (Path.home() / ".bajrang_ai" / "fulfillment_ledger.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    @contextlib.contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self.db_path), timeout=15.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY,
                    email TEXT NOT NULL,
                    amount_paise INTEGER NOT NULL,
                    currency TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payment_id TEXT DEFAULT '',
                    utr_ref TEXT DEFAULT '',
                    license_cert TEXT DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    ts REAL NOT NULL
                );
                """
            )
            conn.commit()

    def log_audit(self, event_type: str, actor: str, detail: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO audit_events (event_type, actor, detail, ts) VALUES (?, ?, ?, ?)",
                (event_type, actor, detail, time.time()),
            )
            conn.commit()

    def create_order(self, email: str, amount_inr: int = 99, utr_ref: str = "") -> Dict[str, Any]:
        order_id = f"order_Bajrang_{secrets.token_hex(6)}"
        amount_paise = int(amount_inr) * 100
        now = time.time()
        status = "pending_verification" if utr_ref else "created"
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO orders (order_id, email, amount_paise, currency, status, utr_ref, created_at, updated_at)
                VALUES (?, ?, ?, 'INR', ?, ?, ?, ?)
                """,
                (order_id, email.strip().lower(), amount_paise, status, utr_ref.strip(), now, now),
            )
            conn.commit()
        self.log_audit("ORDER_CREATED", email.strip().lower(), f"order_id={order_id} amount_paise={amount_paise}")
        return {
            "order_id": order_id,
            "key_id": RAZORPAY_KEY_ID,
            "amount": amount_paise,
            "currency": "INR",
            "email": email.strip().lower(),
            "status": status,
        }

    @staticmethod
    def verify_payment_signature(
        order_id: str,
        payment_id: str,
        signature: str,
        secret: Optional[str] = None,
    ) -> bool:
        signing_secret = secret if secret is not None else RAZORPAY_KEY_SECRET
        if not signing_secret:
            return False
        msg = f"{order_id}|{payment_id}".encode("utf-8")
        expected = hmac.new(signing_secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature.strip().lower())

    @staticmethod
    def verify_webhook_signature(
        raw_body: bytes,
        header_signature: str,
        webhook_secret: Optional[str] = None,
    ) -> bool:
        secret = webhook_secret if webhook_secret is not None else RAZORPAY_WEBHOOK_SECRET
        if not secret:
            return False
        expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, header_signature.strip().lower())

    @staticmethod
    def verify_admin_token(candidate_token: str) -> bool:
        if not candidate_token:
            return False
        candidate_hash = hashlib.sha256(candidate_token.encode("utf-8")).hexdigest()
        return hmac.compare_digest(candidate_hash, ADMIN_PASSKEY_SHA256.lower())

    def fulfill_payment(
        self,
        order_id: str,
        payment_id: str,
        signature: str,
        secret: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.verify_payment_signature(order_id, payment_id, signature, secret=secret):
            self.log_audit("PAYMENT_SIG_INVALID", "razorpay", f"order_id={order_id}")
            return {"ok": False, "error": "Invalid Razorpay HMAC-SHA256 payment signature"}

        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
            if not row:
                return {"ok": False, "error": "Order not found"}
            if row["status"] == "fulfilled" and row["license_cert"]:
                return {
                    "ok": True,
                    "order_id": order_id,
                    "payment_id": row["payment_id"],
                    "license_certificate": row["license_cert"],
                    "idempotent": True,
                }
            cert = AsymmetricLicenseIssuer.issue_license_certificate(
                email=row["email"],
                order_id=order_id,
                payment_id=payment_id,
            )
            conn.execute(
                """
                UPDATE orders
                SET status = 'fulfilled', payment_id = ?, license_cert = ?, updated_at = ?
                WHERE order_id = ?
                """,
                (payment_id, cert, time.time(), order_id),
            )
            conn.commit()
        self.log_audit("ORDER_FULFILLED", row["email"], f"order_id={order_id} payment_id={payment_id}")
        return {
            "ok": True,
            "order_id": order_id,
            "payment_id": payment_id,
            "license_certificate": cert,
            "idempotent": False,
        }

    def admin_approve_order(self, admin_token: str, order_id: str, utr_ref: str = "") -> Dict[str, Any]:
        if not self.verify_admin_token(admin_token):
            self.log_audit("ADMIN_AUTH_FAILED", "admin_api", f"order_id={order_id}")
            return {"ok": False, "status_code": 403, "error": "Unauthorized admin token"}

        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
            if not row:
                return {"ok": False, "status_code": 404, "error": "Order not found"}
            if row["status"] == "fulfilled" and row["license_cert"]:
                return {
                    "ok": True,
                    "status_code": 200,
                    "order_id": order_id,
                    "license_certificate": row["license_cert"],
                    "idempotent": True,
                }
            payment_id = f"upi_verified_{utr_ref or secrets.token_hex(4)}"
            cert = AsymmetricLicenseIssuer.issue_license_certificate(
                email=row["email"],
                order_id=order_id,
                payment_id=payment_id,
            )
            conn.execute(
                """
                UPDATE orders
                SET status = 'fulfilled', payment_id = ?, utr_ref = COALESCE(NULLIF(?, ''), utr_ref),
                    license_cert = ?, updated_at = ?
                WHERE order_id = ?
                """,
                (payment_id, utr_ref, cert, time.time(), order_id),
            )
            conn.commit()
        self.log_audit("ADMIN_ORDER_APPROVED", "owner", f"order_id={order_id}")
        return {
            "ok": True,
            "status_code": 200,
            "order_id": order_id,
            "payment_id": payment_id,
            "license_certificate": cert,
        }

    def list_orders(self, admin_token: str) -> Dict[str, Any]:
        if not self.verify_admin_token(admin_token):
            return {"ok": False, "status_code": 403, "error": "Unauthorized admin token"}
        with self._lock, self._connect() as conn:
            rows = conn.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT 100").fetchall()
            audits = conn.execute("SELECT * FROM audit_events ORDER BY ts DESC LIMIT 100").fetchall()
        return {
            "ok": True,
            "status_code": 200,
            "orders": [dict(r) for r in rows],
            "audit_events": [dict(a) for a in audits],
        }


class _ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def make_payment_http_handler(engine: RazorpayFulfillmentEngine):
    class BajrangPaymentHTTPHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            return

        def _send_json(self, status_code: int, payload: Dict[str, Any]) -> None:
            raw = json.dumps(payload).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Bajrang-Admin-Token, X-Razorpay-Signature")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.end_headers()
            self.wfile.write(raw)

        def _read_body(self) -> bytes:
            length = int(self.headers.get("Content-Length", "0") or "0")
            if length <= 0 or length > 1_048_576:
                return b""
            return self.rfile.read(length)

        def do_OPTIONS(self) -> None:
            self._send_json(200, {"ok": True})

        def do_GET(self) -> None:
            if self.path.startswith("/api/health"):
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "service": "bajrang-razorpay-fulfillment-server",
                        "rsa_bits": RSA_2048_MODULUS.bit_length(),
                    },
                )
                return
            if self.path.startswith("/api/admin/queue"):
                token = self.headers.get("X-Bajrang-Admin-Token", "")
                res = engine.list_orders(token)
                self._send_json(res.get("status_code", 200), res)
                return
            self._send_json(404, {"ok": False, "error": "Route not found"})

        def do_POST(self) -> None:
            raw = self._read_body()
            try:
                body = json.loads(raw.decode("utf-8") or "{}")
            except Exception:
                body = {}

            if self.path == "/api/orders":
                email = str(body.get("email", "")).strip()
                if not email or "@" not in email:
                    self._send_json(400, {"ok": False, "error": "Valid email required"})
                    return
                utr_ref = str(body.get("utr_ref", "")).strip()
                order = engine.create_order(email=email, amount_inr=99, utr_ref=utr_ref)
                self._send_json(200, {"ok": True, "order": order})
                return

            if self.path == "/api/verify-payment":
                order_id = str(body.get("order_id", "")).strip()
                payment_id = str(body.get("payment_id", "")).strip()
                signature = str(body.get("signature", "")).strip()
                res = engine.fulfill_payment(order_id, payment_id, signature)
                self._send_json(200 if res.get("ok") else 400, res)
                return

            if self.path == "/api/webhook":
                sig = self.headers.get("X-Razorpay-Signature", "")
                if not engine.verify_webhook_signature(raw, sig):
                    self._send_json(401, {"ok": False, "error": "Invalid webhook signature"})
                    return
                order_id = str(body.get("order_id", "")).strip()
                payment_id = str(body.get("payment_id", "pay_webhook")).strip()
                if order_id:
                    fake_sig = hmac.new(
                        RAZORPAY_KEY_SECRET.encode("utf-8"),
                        f"{order_id}|{payment_id}".encode("utf-8"),
                        hashlib.sha256,
                    ).hexdigest()
                    res = engine.fulfill_payment(order_id, payment_id, fake_sig)
                    self._send_json(200, res)
                    return
                self._send_json(200, {"ok": True})
                return

            if self.path == "/api/admin/approve":
                token = self.headers.get("X-Bajrang-Admin-Token", "") or str(body.get("admin_token", ""))
                order_id = str(body.get("order_id", "")).strip()
                utr_ref = str(body.get("utr_ref", "")).strip()
                res = engine.admin_approve_order(token, order_id, utr_ref=utr_ref)
                self._send_json(res.get("status_code", 200), res)
                return

            if self.path == "/api/license/verify":
                cert = str(body.get("license_key", "")).strip()
                valid, payload = AsymmetricLicenseIssuer.verify_certificate(cert)
                self._send_json(200, {"ok": valid, "payload": payload})
                return

            self._send_json(404, {"ok": False, "error": "Route not found"})

    return BajrangPaymentHTTPHandler


def serve_payment_server(host: str = "127.0.0.1", port: int = 8787, db_path: Optional[Path] = None) -> None:
    engine = RazorpayFulfillmentEngine(db_path=db_path)
    handler = make_payment_http_handler(engine)
    srv = _ThreadedHTTPServer((host, port), handler)
    print(f"Bajrang Razorpay Fulfillment Server listening on http://{host}:{port} (2048-bit RSA)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.server_close()


def run_self_test() -> int:
    print("Running Razorpay 2048-bit RSA Payment Server self-tests (C1, C2, H5)...")
    assert RSA_2048_MODULUS.bit_length() >= 2048, "RSA modulus must be 2048-bit"
    with tempfile.TemporaryDirectory() as tmp:
        engine = RazorpayFulfillmentEngine(db_path=Path(tmp) / "test_ledger.db")
        handler = make_payment_http_handler(engine)
        srv = _ThreadedHTTPServer(("127.0.0.1", 0), handler)
        port = srv.server_address[1]
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            base_url = f"http://127.0.0.1:{port}"
            with urllib.request.urlopen(f"{base_url}/api/health", timeout=5) as resp:
                health = json.loads(resp.read().decode("utf-8"))
                assert health["ok"] is True and health["rsa_bits"] >= 2048

            req_order = urllib.request.Request(
                f"{base_url}/api/orders",
                data=json.dumps({"email": "student@cbit.ac.in", "utr_ref": "412345678901"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req_order, timeout=5) as resp:
                order_data = json.loads(resp.read().decode("utf-8"))
                assert order_data["ok"] is True
                order_id = order_data["order"]["order_id"]

            req_unauth = urllib.request.Request(
                f"{base_url}/api/admin/approve",
                data=json.dumps({"order_id": order_id}).encode("utf-8"),
                headers={"Content-Type": "application/json", "X-Bajrang-Admin-Token": "wrong-passkey"},
                method="POST",
            )
            try:
                urllib.request.urlopen(req_unauth, timeout=5)
                raise AssertionError("Unauthorized admin approval should return HTTP 403")
            except urllib.error.HTTPError as e:
                assert e.code == 403
                e.close()

            req_auth = urllib.request.Request(
                f"{base_url}/api/admin/approve",
                data=json.dumps({"order_id": order_id, "utr_ref": "412345678901"}).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "X-Bajrang-Admin-Token": "bajrang-server-admin-secret-change-in-env",
                },
                method="POST",
            )
            with urllib.request.urlopen(req_auth, timeout=5) as resp:
                approved = json.loads(resp.read().decode("utf-8"))
                assert approved["ok"] is True
                cert = approved["license_certificate"]
                assert cert.startswith("BAJRANG-V6-")

            lm = LicenseManager(Path(tmp))
            ok_valid, _ = lm.verify_key(cert)
            assert ok_valid is True, "2048-bit RSA server-minted certificate must verify"
            ok_forged, _ = lm.verify_key("BAJRANG-PRO-HACKER-20991231-ZZZZZZZZ")
            assert ok_forged is False, "Forged token must fail"
        finally:
            srv.shutdown()
            srv.server_close()

    print("All Razorpay 2048-bit RSA Payment Server self-tests passed!")
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(run_self_test())
    port_arg = int(os.environ.get("PORT", "8787"))
    serve_payment_server(port=port_arg)
