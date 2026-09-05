# Update the paper-trading bot on your Google Cloud VM

Goal: get the newest code from Lovable onto the already-running VM and restart the bot, without losing paper state.

## Prerequisite: push to GitHub first

The VM only knows about the code that is in the GitHub repository. Lovable does **not** automatically send code to the VM, so you must push the latest version to GitHub before the VM can see it.

1. **If GitHub is already connected**
   - In the Lovable editor, open the **Plus (+)** menu → **GitHub** → push/sync the latest changes.
   - Wait for the push to finish, then open the repo on GitHub and confirm the newest commit is there.

2. **If GitHub is not connected yet**
   - Open **Plus (+)** → **GitHub** → **Connect project**.
   - Authorize the Lovable GitHub App, choose the account/organization, and create the repository.
   - Push the project code.

## Update the VM

1. **Connect to the VM**
   ```bash
   gcloud compute ssh <instance-name> --zone <your-zone>
   ```

2. **Pull the latest code**
   ```bash
   cd /opt/mastermind
   sudo -u mastermind git pull
   ```

3. **Re-run the bootstrap (safe to repeat)**
   ```bash
   sudo bash deploy/setup.sh
   ```
   This refreshes the virtualenv and systemd unit only if something changed.

4. **Restart the bot**
   ```bash
   sudo systemctl restart mastermind
   ```

5. **Verify it is running**
   ```bash
   journalctl -u mastermind -f
   systemctl status mastermind
   sudo -u mastermind /opt/mastermind/.venv/bin/python -m project.main trades --limit 50
   ```

## Notes

- Paper state at `/opt/mastermind/.state/paper_state.json` survives the restart.
- If `git pull` fails because of local changes on the VM, run `sudo -u mastermind git stash` before pulling.
- Add these lines to `.gitignore` in the GitHub repo so the VM does not commit runtime files:
  ```gitignore
  __pycache__/
  *.py[cod]
  .venv/
  .state/
  reports/*.log
  reports/*.csv
  reports/*.jsonl
  ```
- No inbound firewall changes are needed; the bot only makes outbound HTTPS calls.
