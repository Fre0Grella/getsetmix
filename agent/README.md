# gsm-link — the GetSetMix companion

Runs on the machine that has **Rekordbox**, not on the server. Headless: no
window, no tray. Everything you look at stays in the GetSetMix web UI — this
process only answers the questions the server can't reach across a sync folder:

- where did Nextcloud/Syncthing *actually* put the library on this machine?
- where does Rekordbox keep its preferences, and can we point it at our XML?
- do the paths in the XML resolve to files that really exist here?

Standard library only, Python 3.9+. No install, no virtualenv, one file.

## Use it

```bash
# grab it from your own server
curl -fsSLO http://homelab:8765/link/gsm_link.py

python gsm_link.py detect                                   # what it can see
python gsm_link.py pair --server http://homelab:8765 --code 123456
python gsm_link.py doctor                                   # one check, verbose
python gsm_link.py run                                      # keep reporting
```

The pairing code comes from the setup wizard (**Settings ▸ Setup**, or `/setup`).
Config lands in `~/.getsetmix-link.json` — it holds the agent token, so it is
written `0600`.

## `--apply` and the Rekordbox preference

`run`/`doctor --apply` will update Rekordbox's XML path setting for you, but
only when it finds an option that **already exists and already holds an `.xml`
path** — i.e. you've set it once by hand and it's just being repointed. The
config format is undocumented and changes between versions; inventing a key
there is how you corrupt somebody's library. When it can't find one, it reports
`manual` and the wizard shows you the path to paste.

Close Rekordbox first — it rewrites that file on exit. The original is backed up
to `options.json.gsm-backup` before the first write.

## Keeping it running

**Linux** — `~/.config/systemd/user/gsm-link.service`:

```ini
[Unit]
Description=GetSetMix link
[Service]
ExecStart=/usr/bin/python3 %h/gsm_link.py run
Restart=on-failure
[Install]
WantedBy=default.target
```

`systemctl --user enable --now gsm-link`

**macOS** — a LaunchAgent in `~/Library/LaunchAgents` running the same command.

**Windows** — Task Scheduler, "At log on", `pythonw.exe C:\path\gsm_link.py run`.

Or just run `doctor` before a gig; the check is what matters, not the daemon.
