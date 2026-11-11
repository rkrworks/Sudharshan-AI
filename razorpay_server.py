#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bajrang AI Pro (v6.0) — Server-Side Razorpay Order, Webhook Verification & Public-Key License Signer
Implements genuine server-side Razorpay API integration (`POST https://api.razorpay.com/v1/orders`),
`X-Razorpay-Signature` HMAC-SHA256 payment & webhook verification, and asymmetric RSA license signing
so that the private signing key NEVER ships inside client binaries or public web scripts.

Required Environment Variables for Production Deployment:
  - RAZORPAY_KEY_ID          (e.g., rzp_live_... or rzp_test_...)
  - RAZORPAY_KEY_SECRET      (Server-only secret from Razorpay Dashboard)
  - RAZORPAY_WEBHOOK_SECRET  (Server-only webhook secret from Razorpay Dashboard)
  - BAJRANG_PRIVATE_EXP_HEX  (Server-only RSA private exponent D matching PUBLIC_MODULUS_HEX)
"""

import base64
import datetime
import hashlib
import hmac
import json
import os
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, Tuple

from bajrang_core import AsymmetricLicenseVerifier


RAZORPAY_ORDERS_URL = "https://api.razorpay.com/v1/orders"


class RazorpayLicenseBackend:
    """
    Genuine Razorpay Order Creation, Payment Signature Verification, Webhook Verification,
    and Server-Side License Certificate Signing.
    """

    def __init__(
        self,
        key_id: str = "",
        key_secret: str = "",
        webhook_secret: str = "",
        private_d_hex: str = "",
    ) -> None:
        self.key_id = key_id or os.environ.get("RAZORPAY_KEY_ID", "")
        self.key_secret = key_secret or os.environ.get("RAZORPAY_KEY_SECRET", "")
        self.webhook_secret = webhook_secret or os.environ.get("RAZORPAY_WEBHOOK_SECRET", "")
        self.private_d_hex = private_d_hex or os.environ.get("BAJRANG_PRIVATE_EXP_HEX", "")
        self.n_int = int(AsymmetricLicenseVerifier.PUBLIC_MODULUS_HEX, 16)

    def is_configured(self) -> bool:
        return bool(self.key_id and self.key_secret)

    def create_razorpay_order(self, amount_inr: int, receipt_id: str, notes: Dict[str, str]) -> Tuple[bool, Dict[str, Any]]:
        if not self.is_configured():
            return (
                False,
                {
                    "error": "Razorpay server credentials (RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET) are not configured on the backend.",
                    "status": "configuration_required",
                },
            )
        payload = {
            "amount": int(amount_inr) * 100,
            "currency": "INR",
            "receipt": receipt_id,
            "notes": notes,
        }
        auth_raw = f"{self.key_id}:{self.key_secret}".encode("utf-8")
        auth_b64 = base64.b64encode(auth_raw).decode("ascii")
        try:
            req = urllib.request.Request(
                RAZORPAY_ORDERS_URL,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Basic {auth_b64}",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return True, data
        except Exception as exc:
            return False, {"error": f"Razorpay Order creation failed: {exc}"}

    def verify_payment_signature(
        self,
        razorpay_order_id: str,
        razorpay_payment_id: str,
        razorpay_signature: str,
    ) -> bool:
        if not self.key_secret or not razorpay_order_id or not razorpay_payment_id or not razorpay_signature:
            return False
        msg = f"{razorpay_order_id}|{razorpay_payment_id}".encode("utf-8")
        expected = hmac.new(self.key_secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, razorpay_signature)

    def verify_webhook_signature(self, raw_body: bytes, header_signature: str) -> bool:
        if not self.webhook_secret or not raw_body or not header_signature:
            return False
        expected = hmac.new(self.webhook_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, header_signature)

    def sign_license_certificate(
        self,
        subscriber_email: str,
        plan: str,
        order_id: str,
        payment_id: str,
        days_valid: int = 30,
        private_d_int: int = 0,
    ) -> str:
        d_val = private_d_int or (int(self.private_d_hex, 16) if self.private_d_hex else 0)
        if d_val <= 0:
            raise ValueError("Server private signing exponent (BAJRANG_PRIVATE_EXP_HEX) is required to sign certificates.")
        exp_date = (datetime.date.today() + datetime.timedelta(days=days_valid)).isoformat()
        payload = {
            "sub": subscriber_email.strip().lower(),
            "plan": plan,
            "exp": exp_date,
            "order_id": order_id,
            "payment_id": payment_id,
        }
        payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode("ascii").rstrip("=")
        digest_int = int.from_bytes(hashlib.sha256(payload_bytes).digest(), "big") % self.n_int
        sig_int = pow(digest_int, d_val, self.n_int)
        sig_hex = format(sig_int, "x")
        return f"BAJRANG-V6-{payload_b64}.{sig_hex}"
