# Go-Live Guide — Crypto Bot on Oracle Free Tier (free 24/7) + live web

_How to run the bot for REAL money, free, without your PC — and keep the dashboard updating._

---

## 0. Read first (reality check)
- The bot is **PAPER** right now: it computes signals + tracks a fake $10k, **places no real orders**.
- Going live = **real money**. Two separate things are needed:
  - **(A) Infra** — a free 24/7 box that can reach Binance (this guide, steps 1–5).
  - **(B) Live order-execution module** — code that actually places exchange orders. **NOT built yet** (step 6). `paper_bot.py` only simulates.
- Your edge is **not live-proven** (the dashboard banner: "nothing has survived a live regime change"). So: infra first, then testnet, then **tiny** real size.

---

## 1. Oracle Cloud "Always Free" VM (free forever, Binance-reachable)
Why Oracle: its free tier is **permanent** (not a 12-month trial) and lets you pick an **Asian region** so Binance isn't geo-blocked (Google/AWS free regions are US → blocked).

1. Sign up at **cloud.oracle.com** → choose **"Always Free" eligible**. (Needs a card for identity; not charged on free resources.)
2. **Home region: Singapore** (or Tokyo) — pick at signup, can't change later. This is what makes Binance reachable.
3. Create a **Compute instance**:
   - Image: **Ubuntu 22.04**.
   - Shape: **VM.Standard.A1.Flex** (Ampere ARM — up to 4 OCPU / 24GB free) OR **VM.Standard.E2.1.Micro** (AMD, always-free). Either is plenty.
   - Download the **SSH private key** when prompted (you only get it once).
4. SSH in: `ssh -i your-key.pem ubuntu@<public-ip>`

## 2. Deploy the bot on the VM
```bash
sudo apt update && sudo apt install -y python3-pip git
git clone https://github.com/Lemonef/Trade.git
cd Trade && pip3 install requests pandas numpy markdown
python3 live_bot/paper_bot.py        # smoke test — should write web/data.json, no errors
```
(From Singapore, `api.binance.com` works — no 451. The vision fallback still covers you.)

## 3. Secrets — env vars, NEVER in the repo
```bash
cat > ~/.bot_env <<'EOF'
export BINANCE_KEY="..."          # exchange API key (trade-enabled) — for LIVE only
export BINANCE_SECRET="..."
export GH_TOKEN="..."             # GitHub token (repo write) — to push data.json to the dashboard
EOF
chmod 600 ~/.bot_env              # readable only by you
```
Keys live on the VM only. Never commit them. For the PAPER stage you only need `GH_TOKEN`.

## 4. Schedule it (cron, every 4h — matches the current cadence)
```bash
cat > ~/Trade/run.sh <<'EOF'
#!/bin/bash
cd ~/Trade && . ~/.bot_env
git pull -q
python3 live_bot/paper_bot.py
git add web/data.json web/health.json
git -c http.extraheader="AUTHORIZATION: bearer $GH_TOKEN" commit -m "bot run $(date -u +%FT%TZ)" -q || true
git -c http.extraheader="AUTHORIZATION: bearer $GH_TOKEN" push -q || true
EOF
chmod +x ~/Trade/run.sh
crontab -e   # add:
# 5 */4 * * * /home/ubuntu/Trade/run.sh >> /home/ubuntu/bot.log 2>&1
```
Now the VM runs the bot every 4h forever, for $0.

## 5. The WEB — how the dashboard stays live
**Nothing about the dashboard changes.** It's GitHub Pages reading `web/data.json` from the Trade repo — it's **read-only and doesn't care where data.json came from**.

- **Now:** GitHub Actions writes `data.json` → pushes → Pages serves.
- **Live:** the **VM** writes `data.json` (now REAL equity) → pushes → Pages serves the same way.
- The freshness badge + `health.json` heartbeat already work — they'll just reflect the VM's runs.
- **Choice:** either (a) move the whole bot to the VM and **turn off** the GitHub Actions `paper-bot` (avoid both pushing), or (b) keep GitHub Actions for the **stocks/scans** pages (spike side) and let the VM own only `data.json` (crypto). Cleanest = the VM owns crypto `data.json`; GitHub Actions keeps doing stocks/scans.

So: **point the data.json writer at the VM, leave the dashboard alone.** It shows live real-money state automatically.

## 6. ⚠️ The missing piece — LIVE ORDER EXECUTION (build before real money)
`paper_bot.py` updates a **simulated** ledger; it does **not** call the exchange. To trade live you must add an execution layer:
- Use **`ccxt`** or **`python-binance`** to place real **spot** orders on each signal (market or limit).
- Read **real balances + fills** from the exchange and reconcile state **from the exchange**, not the JSON sim.
- **Gold = easy** (buy & hold PAXG spot). **Funding/Carry = hard** (spot + perp short on Futures — region-check Binance Futures availability in TH; skip at first).
- **Always test on Binance Testnet first** (free fake money, real API), then go tiny.

This is a real build — keep it to **ONE** strategy (e.g. Donchian or Book v2, spot only) to start.

## 7. Order of operations
1. **Oracle VM up** (steps 1–2).
2. **Cron the PAPER bot on the VM** (steps 3–5) → proves infra + the web-push works from the VM, $0.
3. **Build + Testnet the execution module** (step 6) — no real money yet.
4. **Go live tiny** — one strategy, ~$100–500, watch fills/fees/slippage vs paper.
5. **Scale only after a live regime change** (the real gate).

---
_Infra cost = $0 on Oracle Always Free. The real gate is the edge being live-proven, not the hosting._
