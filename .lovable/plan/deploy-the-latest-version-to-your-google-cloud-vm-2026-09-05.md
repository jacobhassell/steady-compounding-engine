# Deploy the latest version to your Google Cloud VM

Goal: update the already-running paper-trading bot on your GCE VM with the newest code (including the new trade-history logging), without losing paper state.

## Steps

1. **Connect to the VM**
   ```bash
   gcloud compute ssh <instance-name> --zone <your-zone>
   ```

2. **Pull the latest code**
   ```bash
   cd /opt/mastermind
   sudo git pull
   ```

3. **Re-run the bootstrap (idempotent)**
   Run this whenever dependencies in `project/requirements.txt` may have changed:
   ```bash
   sudo bash deploy/setup.sh
   ```
   This refreshes the virtualenv, reinstalls dependencies, and reinstalls the systemd unit if needed.

4. **Restart the service**
   ```bash
   sudo systemctl restart mastermind
   ```

5. **Verify the new version is running**
   - Live logs: `journalctl -u mastermind -f`
   - Service status: `systemctl status mastermind`
   - New trade-history output:
     ```bash
     sudo -u mastermind /opt/mastermind/.venv/bin/python -m project.main trades --limit 50
     ```
   - Files to expect:
     - `/opt/mastermind/reports/fills.csv`
     - `/opt/mastermind/reports/trades.csv`
     - `/opt/mastermind/reports/events.jsonl`

## Notes

- Paper state at `/opt/mastermind/.state/paper_state.json` survives the restart.
- If `git pull` fails because of local changes, the plan includes a step to stash or reset them safely.
- No inbound firewall changes are needed; the bot only makes outbound HTTPS calls.
