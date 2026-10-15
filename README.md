# snap-watch (cloud backup)

GitHub Actions copy of a Eurostar Snap availability poller.
- Every 5 min (self-looping job, ~5.5h per run, restarts itself until the last date): checks `config.cloud.json` dates, ntfy.sh urgent push to `NTFY_TOPIC` secret when a date opens.
- No basket (that only works from the Mac, so it opens in your Chrome). State kept in Actions cache.
- Stop: `gh workflow disable poll -R TimSHGH/snap-watch`.
