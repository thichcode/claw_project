# RCA Full Async (stdlib)

Python script for asynchronous RCA pipeline:
- Zabbix + UptimeRobot ingest
- Correlation by event time window (±10 minutes)
- SQLite TTL cache
- Batch processing with controlled concurrency
- Multi-agent RCA (collector/correlation/hypothesis/verifier/decision)
- Metric trend + anomaly scoring (CPU/memory/disk/network/process/log)
- Smart input parsing (JSON fields + raw text + URL extraction)
- Microsoft Teams webhook output
- Optional ServiceDesk Plus v14720+ flow:
  1) update solution
  2) add exactly 1 task
  3) close that task
  4) add worklog
  5) close ticket
- KB matching from JSON and auto-attach KB ID into RCA + SDP
- Confidence calibration + guardrail mode (avoid overconfident RCA)
- Report output aligned to `sample_rca.txt` format (`rca` + `summary_markdown` + structured `timeline`)
- Datetime parsing/formatting standardized to GMT+7 (Asia/Saigon)

## Run

Single-agent (current stable):

```bash
python rca_full_async_stdlib.py
```

Multi-agent (OpenClaw-style roles):

```bash
python rca_multi_agent.py
```

With input payload (request_id taken from input, and can include only `hostname` + `eventid`):

```bash
python rca_multi_agent.py --input-json input.json
```

Input also supports:
- `raw_input`, `subject`, `description_text` (auto-parse hostname/eventid/request_id)
- `url` with SDP links (`woID=...`, `/requests/...`, `/workorder/...`)
- `kb_json` or `kb_path` (path to KB JSON file for KB ID matching)

Override request id explicitly:

```bash
python rca_multi_agent.py --request-id 123456
```

## Ollama support

Yes, dùng Ollama **ok** nếu bật OpenAI-compatible API.

Ví dụ:

```bash
export LLM_API_KEY=ollama
export LLM_MODEL=qwen2.5:7b-instruct
export LLM_URL=http://127.0.0.1:11434/v1/chat/completions
python rca_full_async_stdlib.py
```

Nếu không set `LLM_API_KEY` thì script vẫn chạy, chỉ dùng fallback RCA text.

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
- `ENRICH_LOOKBACK_MINUTES` (default: `20`)
- `ENRICH_TOP_N_ITEMS` (default: `5`)
- `ENRICH_ITEM_KEY_HINTS` (default: `system.cpu,vm.memory,vfs.fs,net.if,proc.num,log,kubelet,docker,mysql`)
- `TTL_ZABBIX_SEC` (default: `90`)
- `TTL_UPTIME_SEC` (default: `180`)
- `TTL_LLM_SEC` (default: `600`)
- `SDP_URL` (ví dụ: `https://helpdesk.example.com`)
- `SDP_TECHNICIAN_KEY`
- `SDP_REQUEST_ID`
- `SDP_TASK_TITLE` (default: `RCA investigation`)
- `SDP_TASK_OWNER` (optional)
- `SDP_RESOLUTION_PREFIX` (default: `[AUTO RCA]`)
- `SDP_CLOSE_STATUS` (default: `Closed`)
- `KB_JSON_PATH` (optional, default KB file path)
- `KB_MATCH_MIN_SCORE` (default: `0.2`, threshold for KB matching)

## Output format

`rca_multi_agent.py` report now returns JSON string with:

- `rca.root_cause`
- `rca.contributing_factors`
- `rca.impact`
- `rca.resolution`
- `rca.timeline` (array of `{time, event}`)
- `rca.lessons_learned`
- `rca.actionable_steps_for_L1`
- `rca.metadata` (confidence calibrated/raw, guardrail_mode, kb_id, kb_match_score, anomaly highlights, correlation counts, SDP state)
- `summary_markdown`

Reference samples:
- `sample_rca.txt` (normal mode)
- `sample_rca_guardrail_on.txt` (guardrail mode)
