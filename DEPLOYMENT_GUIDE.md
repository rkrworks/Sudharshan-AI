# SUDHARSHAN AI — PRODUCTION DEPLOYMENT GUIDE

**Target Audience**: DevOps Engineers, System Administrators, and Maintainers  
**Author**: Kaushik Ram Ravuru (B.E. IT, Section IT-1, CBIT Hyderabad)  
**Project**: Sudharshan AI (Alpha v0.9)  

---

## 1. Static Web Portal Deployment (Vercel & GitHub Pages)

### Vercel Deployment Architecture
The web portal for Sudharshan AI uses a strictly isolated static distribution directory (`web/`) to prevent leaking repository backend code, tests, or internal SQLite databases.

- **Configuration File (`vercel.json`)**:
  ```json
  {
    "cleanUrls": true,
    "trailingSlash": false,
    "outputDirectory": "web"
  }
  ```
- **Deployment Steps**:
  1. Link the repository to your Vercel project:
     ```bash
     vercel link
     ```
  2. Deploy to production:
     ```bash
     vercel --prod
     ```
  3. Ensure the project root directory is set to repository root so Vercel detects `vercel.json` and serves `web/`.

### GitHub Pages Deployment
- Handled automatically by `.github/workflows/deploy.yml` on push to the `main` branch.
- Actions step uploads `path: "web"` ensuring zero backend files are published to GitHub Pages.

---

## 2. Cryptographic Backend Server Deployment (`razorpay_server.py`)

The payment fulfillment and RSA license signing server should be hosted on a secure cloud VM or container (e.g. AWS Lightsail, DigitalOcean Droplet, Render, or Railway).

### Environment Variables
Configure the following environment variables on the production server:

```bash
# Server Port & Host
export BAJRANG_HOST="0.0.0.0"
export BAJRANG_PORT="8080"

# Admin Key for protected /api/admin/* endpoints
export BAJRANG_ADMIN_KEY="<strong-random-32-byte-hex>"

# Razorpay Credentials (from Razorpay Dashboard)
export RAZORPAY_KEY_ID="rzp_live_xxxxxxxxxxxx"
export RAZORPAY_KEY_SECRET="xxxxxxxxxxxxxxxxxxxxxxxx"
export RAZORPAY_WEBHOOK_SECRET="xxxxxxxxxxxxxxxxxxxxxxxx"

# 2048-bit RSA Private Signing Key (D Exponent in Hex)
export BAJRANG_RSA_D_HEX="<secure-2048-bit-private-key-hex>"
```

### Systemd Service Configuration (`/etc/systemd/system/sudharshan-server.service`)
```ini
[Unit]
Description=Sudharshan AI RSA License & Payment Server
After=network.target

[Service]
Type=simple
User=sudharshan
WorkingDirectory=/opt/sudharshan-server
ExecStart=/usr/bin/python3 /opt/sudharshan-server/razorpay_server.py
Restart=always
RestartSec=3
EnvironmentFile=/etc/sudharshan/server.env

[Install]
WantedBy=multi-user.target
```

---

## 3. Local Desktop Client Distribution

### Windows 11 Build & Packaging
- Windows bundle files are packaged into a clean archive:
  - `bajrang_core.py`
  - `windows.py` (and alias `bajrang_windows.py`)
  - `installer_windows.py`
  - `requirements_windows.txt`
  - `setup_windows.bat`
- Attach the generated release archive to GitHub Releases (`v0.9-alpha`).

### Fedora Linux Packaging
- Create the standard tarball with execution permissions set:
  ```bash
  tar -czf Sudharshan_AI_Fedora_v0.9.tar.gz bajrang_core.py fedora.py bajrang_llama32.py setup_fedora.sh requirements_fedora.txt README.md
  ```
- Distribute via GitHub Releases and provide the curl one-liner:
  ```bash
  curl -fsSL https://raw.githubusercontent.com/rkrworks/Sudharshan-AI/main/setup_fedora.sh | bash
  ```
