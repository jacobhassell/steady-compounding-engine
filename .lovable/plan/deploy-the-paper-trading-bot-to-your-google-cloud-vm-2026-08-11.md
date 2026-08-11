# Deploy the paper-trading bot to your Google Cloud VM

Goal: the Python engine in `project/` runs continuously on your existing GCE VM, survives crashes and reboots, and keeps its paper state and journal on disk.

The React dashboard is not part of this — it stays on Lovable. Only the Python bot goes on the VM.

## What I'll add to the repo

Three small files so the deploy is copy-paste instead of improvised:

- `deploy/mastermind.service` — systemd unit that runs `python -m project.main paper --cycles 0`, restarts on failure, starts on boot.
- `deploy/setup.sh` — one-shot VM bootstrap: installs Python, creates the venv, installs `project/requirements.txt`, sets UTC, installs and enables the service.
- `deploy/README.md` — the runbook below, plus log/state locations and update instructions.

I'll also add `.state/` and `reports/` to `.gitignore` so paper state and the journal never get committed.

## Step-by-step runbook

**1. Connect to the VM**
From the Cloud Console, click SSH next to the instance, or locally:
`gcloud compute ssh <instance-name> --zone <your-zone>`

**2. Get the code onto the VM**
Push this project to GitHub from Lovable, then on the VM:
`sudo git clone <repo-url> /opt/mastermind`

**3. Run the bootstrap**
`cd /opt/mastermind && sudo bash deploy/setup.sh`
This installs `python3-venv`, builds `/opt/mastermind/.venv`, installs dependencies, and sets the host clock to UTC (the exchange-session logic assumes UTC).

**4. Smoke-test before going continuous**
`sudo -u mastermind /opt/mastermind/.venv/bin/python -m project.main scan`
One scan cycle. You should see ranked candidates. If Yahoo throttles the VM's IP, you'll see skipped symbols in the log rather than a crash.

**5. Start it for real**
`sudo systemctl enable --now mastermind`

**6. Watch it**
- Live logs: `journalctl -u mastermind -f`
- Journal file: `/opt/mastermind/reports/journal.log`
- Paper state: `/opt/mastermind/.state/paper_state.json` (equity, cash, open and closed positions)
- Status: `systemctl status mastermind`

**7. Update after a code change**
`cd /opt/mastermind && sudo git pull && sudo systemctl restart mastermind`
Paper state survives the restart; the trader reloads from disk rather than starting flat.

## Sizing and cost notes

- An `e2-micro` is enough — the bot is idle between scan windows. That instance type is also inside GCP's always-free tier in `us-west1`, `us-central1`, and `us-east1`.
- No inbound ports need opening. The bot only makes outbound HTTPS calls to Yahoo. Leave the firewall as-is.
- If the VM is preemptible/Spot, systemd's `Restart=always` covers restarts, but a preemption mid-session loses nothing because state is written every cycle.

## Technical details

- Runs as a dedicated unprivileged `mastermind` user, with `WorkingDirectory=/opt/mastermind` so the relative `.state/` and `reports/` paths resolve correctly.
- `Restart=always`, `RestartSec=30` — transient Yahoo failures already self-heal inside `ResilientProvider`; systemd covers hard process death.
- `--cycles 0` means run forever; the loop sleeps until the next scan window via `engine.sleep_seconds()`.
- Live trading stays inert: nothing sends real orders unless the `live` command is run with both `--no-dry-run` and `--arm`.
