# Deploying Mastermind to a Google Cloud VM (paper trading)

The Python engine in `project/` runs continuously on a small Linux VM. The React
dashboard is separate and stays on Lovable — nothing here serves HTTP, and no
inbound ports need to be opened.

An `e2-micro` in `us-west1`, `us-central1`, or `us-east1` is enough and sits
inside GCP's always-free tier. The bot is idle between scan windows.

## 1. Connect to the VM

From the Cloud Console, click **SSH** next to the instance, or from your machine:

```bash
gcloud compute ssh <instance-name> --zone <your-zone>
```

## 2. Put the code on the VM

Push this project to GitHub from Lovable, then on the VM:

```bash
sudo apt-get update && sudo apt-get install -y git
sudo git clone <repo-url> /opt/mastermind
```

The path matters — the systemd unit expects `/opt/mastermind`.

## 3. Bootstrap

```bash
cd /opt/mastermind
sudo bash deploy/setup.sh
```

This installs Python, creates `/opt/mastermind/.venv`, installs
`project/requirements.txt`, sets the host clock to UTC (the exchange-session
logic assumes UTC), creates an unprivileged `mastermind` user, and installs the
systemd unit. It is safe to re-run.

## 4. Smoke-test before going continuous

```bash
sudo -u mastermind /opt/mastermind/.venv/bin/python -m project.main scan
```

One scan cycle, printing ranked candidates. If Yahoo Finance throttles the VM's
IP you will see skipped symbols in the log rather than a crash —
`ResilientProvider` retries, backs off, and blacklists persistent failures.

Optional sanity checks before committing capital to the simulation:

```bash
cd /opt/mastermind
.venv/bin/python -m project.main backtest --tickers AAPL,MSFT,NVDA --bars 500
.venv/bin/python -m project.main optimize --tickers AAPL,MSFT,NVDA --bars 800
```

Reject anything whose walk-forward efficiency is below 0.35 — that is curve
fitting, not an edge.

## 5. Start it

```bash
sudo systemctl enable --now mastermind
```

`enable` makes it start on boot; `--now` starts it immediately.

## 6. Watch it

| What | Command / path |
|---|---|
| Live logs | `journalctl -u mastermind -f` |
| Service status | `systemctl status mastermind` |
| Narrative journal | `/opt/mastermind/reports/journal.log` |
| Paper state | `/opt/mastermind/.state/paper_state.json` |
| Recent errors only | `journalctl -u mastermind -p err --since today` |

`paper_state.json` holds cash, realized PnL, open positions with their ladder
stage, closed positions, and the last 200 journal lines. It is rewritten every
cycle, so a crash or preemption loses at most one cycle.

## 7. Update after a code change

```bash
cd /opt/mastermind
sudo git pull
sudo bash deploy/setup.sh          # only needed if dependencies changed
sudo systemctl restart mastermind
```

## 8. Stop

```bash
sudo systemctl stop mastermind     # stop now
sudo systemctl disable mastermind  # and don't start on boot
```

## Operational notes

- **Restarts.** `Restart=always` with a 30-second delay. Transient data failures
  already self-heal inside the scan loop; systemd covers hard process death.
- **Preemptible / Spot VMs.** Fine for paper trading. State is written every
  cycle and the unit restarts on boot.
- **Datacenter IPs.** Yahoo Finance rate-limits cloud ranges more aggressively
  than home connections. Expect more skipped symbols than on a laptop. If it
  gets severe, raise `data.retry_backoff_seconds` in `project/config/settings.py`
  and lengthen the scan interval.
- **Live trading stays inert.** This unit runs the `paper` command. Real orders
  require running the `live` command with **both** `--no-dry-run` and `--arm`,
  and typing the confirmation phrase. Do not change the unit's `ExecStart` until
  you have watched a full month of paper cycles.
