# OpenClaw Monitor

Lightweight monitoring project to stream `openclaw` logs via SSE and read them in a single-page dark reader.

## Backend
Start the backend on port 3005 (or set PORT to another port):
```bash
cd backend
PORT=3005 npm run start
```

1. `cd backend`
2. `npm install`
3. `npm start` (or `npm run dev`)
   - listens on http://localhost:3005
   - endpoints: `/health`, `/api/status`, `/api/logs/stream`
   - will run `openclaw logs --follow`; if unavailable, falls back to `journalctl --user -u openclaw -f -n 50`
   - lines parsed to `{ ts, level, source, message }`

## Frontend
1. `cd frontend`
2. `npm install`
3. `PORT=3006 npm start` (or `npm run dev` for hot reload)
   - listens on http://localhost:3006
   - single-page UI with log viewer, filters, pause/resume, and download button

## Combined
1. Start backend (`PORT=3005 npm start`, or set `PORT=3005`)
2. Start frontend (`PORT=3006 npm start`) and open http://localhost:3006

## Notes
- Use `scripts/track_command.sh <command>` in backend folder to log commands to `logs/commands.json` and view via `docs/command-tracker.html`.
- The frontend auto-reconnects SSE and shows clear errors if `openclaw` or `journalctl` fail.

Finally, run `openclaw dashboard`, `openclaw logs --follow`, `openclaw status --all` to compare live activity.
