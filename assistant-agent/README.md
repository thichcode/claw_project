# Assistant Agent

This is the v1 autonomous assistant backend based on your architecture.

## Quick start

```bash
cd assistant-agent
python -m venv .venv
.venv\Scripts\activate
pip install fastapi pydantic uvicorn
set PYTHONPATH=C:\Users\Lenovo\.openclaw\workspace\assistant-agent
uvicorn assistant_agent.api.main:app --port 8000
```

## API

- `POST /tasks` - Create a task with a goal
- `GET /tasks/{id}` - Get task status and results
- `POST /tasks/{id}/run` - Execute the task

## Demo

```bash
# Create task
curl -X POST http://localhost:8000/tasks -H "Content-Type: application/json" -d "{\"goal\": \"Find 3 marketing ideas for coffee shop\"}"

# Run task
curl -X POST http://localhost:8000/tasks/{task_id}/run"

# Check results
curl http://localhost:8000/tasks/{task_id}
```
