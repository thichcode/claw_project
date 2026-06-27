#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8080}"

curl -sS "$BASE_URL/api/health"

task_json=$(curl -sS -X POST "$BASE_URL/api/tasks" \
  -H 'content-type: application/json' \
  -d '{"goal":"Tìm 5 nguồn, tóm tắt lại, viết draft email","requested_by":"smoke-user"}')

echo "$task_json"
task_id=$(python -c 'import json,sys; print(json.loads(sys.stdin.read())["request_id"])' <<< "$task_json")

curl -sS -X POST "$BASE_URL/api/tasks/$task_id/run"
curl -sS "$BASE_URL/api/tasks/$task_id"

echo "Smoke flow done for task_id=$task_id"
