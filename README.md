# snap-watch (cloud backup)

GitHub Actions copy of the Eurostar Snap poller (source of truth: `insights-and-client-work/client_work_python/tim_work/projects/snap_watch`).
- Every 5 min (GitHub cron, often delayed): checks `config.cloud.json` dates, ntfy.sh urgent push to `NTFY_TOPIC` secret when a date opens.
- No basket (that only works from the Mac, so it opens in your Chrome). State kept in Actions cache.
- Stop: `gh workflow disable poll -R TimSHGH/snap-watch`.
