# Zilo WAHA nodes on Hetzner

Start with one node: `wa-1` manages up to 10 active linked businesses. Create
`wa-2` once `wa-1` reaches 8 active businesses, so it is ready before the
first node reaches its operating cap. A session is persisted locally on its
assigned node; do not move or duplicate its session directory while it is
logged in.

## Server size

Start each node with a Hetzner **CPX22** (2 vCPU, 4 GB RAM, 80 GB SSD). The
10-business operating cap leaves enough headroom for GOWS reconnects and
history syncs. WAHA itself runs without a browser when using the GOWS image.

## One-time setup on each Ubuntu server

1. Point a DNS record such as `wa-1.example.com` to the server's public IP.
2. Install Docker Engine and the Docker Compose plugin.
3. Copy this folder to `/opt/zilo-waha`, copy `.env.example` to `.env`, and set
   unique values for the domain, worker id, and API key.
4. Create the persistent paths before the first start:

   ```bash
   mkdir -p /opt/zilo-waha/data/sessions /opt/zilo-waha/data/media
   ```

5. From `/opt/zilo-waha`, start it with `docker compose up -d`.
6. Allow only SSH, HTTP, and HTTPS in Hetzner's firewall. Port 3000 must not be
   public; Caddy is the HTTPS gateway.

## Zilo backend configuration

Set these values in the deployed Zilo backend. Use the same WAHA API key on
both nodes. Zilo deterministically assigns a business to one node on its first
link and records that assignment in its WhatsApp record, so later sends, QR
refreshes, and history syncs stay on that node.

```text
WHATSAPP_PROVIDER=waha
WAHA_API_URLS=https://wa-1.example.com
WAHA_API_KEY=<the same WAHA_API_KEY configured on both nodes>
WAHA_WEBHOOK_SECRET=<a separate long random secret shared with Zilo only>
WEBHOOK_BASE_URL=https://<your-zilo-api-domain>
```

`WAHA_WEBHOOK_SECRET` is sent as a SHA-512 HMAC with every WAHA event and is
verified by Zilo before it processes a message or connection change. Do not use
the WAHA API key as the webhook secret.

When `wa-2` is added, update `WAHA_API_URLS` to
`https://wa-1.example.com,https://wa-2.example.com` and redeploy Zilo. Existing
businesses remain on `wa-1`; Zilo assigns only newly linked businesses across
the two nodes.

## Operations

- Back up `data/sessions` daily, encrypted and off-server. This is the WhatsApp
  auth state; losing it forces customers to link again.
- Keep a server-specific inventory of which business is on which node.
- Monitor HTTPS availability, container restarts, memory, and the number of
  sessions in `FAILED` or `SCAN_QR_CODE` state.
- The WAHA dashboard is disabled in production because Zilo handles linking;
  enable it temporarily only for emergency diagnostics, then disable it again.
- Upgrade one node first, observe it for 24 hours, then upgrade the other.
- Never refresh a pairing code by deleting a session. Zilo's `/whatsapp/refresh`
  route requests a new code while retaining the current session.
