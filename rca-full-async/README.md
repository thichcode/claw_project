# RCA Full Async (stdlib)

Python script for asynchronous RCA pipeline:
- Zabbix + UptimeRobot ingest
- Correlation by event time window (±10 minutes)
- SQLite TTL cache
- Batch processing with controlled concurrency
- Optional LLM summary
- Microsoft Teams webhook output

## Run

```bash
python rca_full_async_stdlib.py
```

## Environment variables

- `ZABBIX_URL`
- `ZABBIX_TOKEN`
- `UPTIMEROBOT_API_KEY`
- `TEAMS_WEBHOOK_URL`
- `LLM_API_KEY` (optional)
- `LLM_MODEL` (default: `gpt-4o-mini`)
- `LOOKBACK_MINUTES` (default: `30`)
- `TIME_WINDOW_MINUTES` (default: `10`)
- `BATCH_SIZE` (default: `20`)
- `MAX_CONCURRENCY` (default: `8`)
- `TTL_ZABBIX_SEC` (default: `90`)
- `TTL_UPTIME_SEC` (default: `180`)
- `TTL_LLM_SEC` (default: `600`)
