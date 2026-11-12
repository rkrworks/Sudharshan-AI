/**
 * Bajrang AI Pro (v6.0) — Client License & Order Verification Helper
 * 
 * Secure client-side communication with `razorpay_server.py`:
 *   - /api/orders
 *   - /api/admin/queue
 *   - /api/admin/approve
 *   - /api/verify
 * 
 * Strict Security Audit Compliance:
 *   - NO hardcoded OWNER credentials or backdoor passkeys
 *   - NO client-side pseudo-license generation
 *   - NO embedded base64 binary payloads
 *   - All cryptographic license verification is delegated to server-signed RSA-2048 BAJRANG-V6- certificates
 */

(function (root, factory) {
  if (typeof define === 'function' && define.amd) {
    define([], factory);
  } else if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.BajrangPortal = factory();
  }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const DEFAULT_API_BASE = window.location.origin;

  async function createOrder(email, amount = 99, plan = 'pro_monthly') {
    const res = await fetch(`${DEFAULT_API_BASE}/api/orders`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: email.trim(), amount, plan })
    });
    return res.json();
  }

  async function verifyCertificate(certificate) {
    const res = await fetch(`${DEFAULT_API_BASE}/api/verify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ certificate: certificate.trim() })
    });
    return res.json();
  }

  async function fetchAdminQueue(adminKey = '') {
    const headers = { 'Content-Type': 'application/json' };
    if (adminKey) headers['X-Admin-Key'] = adminKey;
    const res = await fetch(`${DEFAULT_API_BASE}/api/admin/queue`, {
      method: 'GET',
      headers
    });
    return res.json();
  }

  async function approveOrder(orderId, email, plan = 'pro_monthly', adminKey = '', daysValid = 30) {
    const headers = { 'Content-Type': 'application/json' };
    if (adminKey) headers['X-Admin-Key'] = adminKey;
    const res = await fetch(`${DEFAULT_API_BASE}/api/admin/approve`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ order_id: orderId, email, plan, admin_key: adminKey, days_valid: daysValid })
    });
    return res.json();
  }

  return {
    createOrder,
    verifyCertificate,
    fetchAdminQueue,
    approveOrder,
    VERSION: '6.0.0-hardened'
  };
});
