const express = require('express');
const { spawn } = require('child_process');
const cors = require('cors');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3001;

app.use(cors());
app.use(express.json());

const parseLine = (line) => {
  const match = line.match(/^(?<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)\s+(?<level>\w+)\s+(?<source>[^\s]+):\s*(?<msg>.*)$/);
  if (match) {
    const { ts, level, source, msg } = match.groups;
    return { ts, level, source, message: msg };
  }
  return { ts: new Date().toISOString(), level: 'info', source: 'openclaw-log', message: line };
};

const spawnLogger = () => {
  let cmd = 'openclaw';
  let args = ['logs', '--follow'];
  const proc = spawn(cmd, args);
  proc.on('error', () => {
    const fallback = spawn('journalctl', ['--user', '-u', 'openclaw', '-f', '-n', '50']);
    fallback.stderr.on('data', () => {});
    return fallback;
  });
  return proc;
};

const createLogStream = () => {
  let proc = spawnLogger();
  return (onLine) => {
    const parser = (chunk) => {
      chunk
        .toString()
        .split('\n')
        .filter(Boolean)
        .forEach((line) => onLine(parseLine(line)));
    };
    proc.stdout.on('data', parser);
    proc.stderr.on('data', parser);
    proc.on('exit', (code) => {
      if (code !== 0) {
        proc = spawnLogger();
        proc.stdout.on('data', parser);
        proc.stderr.on('data', parser);
      }
    });
    return () => {
      proc.kill();
    };
  };
};

const logStream = createLogStream();
const history = [];

app.get('/health', (req, res) => {
  res.json({ ok: true, ts: new Date().toISOString() });
});

app.get('/api/status', (req, res) => {
  const status = { ts: new Date().toISOString(), process: process.pid, history: history.slice(-10) };
  res.json(status);
});

app.get('/api/logs/stream', (req, res) => {
  res.set({
    Connection: 'keep-alive',
    'Content-Type': 'text/event-stream',
    'Cache-Control': 'no-cache'
  });
  res.flushHeaders();

  const send = (entry) => {
    history.push(entry);
    res.write(`data: ${JSON.stringify(entry)}\n\n`);
  };
  send({ ts: new Date().toISOString(), level: 'info', source: 'server', message: 'client connected' });

  const cleanup = logStream(send);
  req.on('close', () => cleanup());
});

app.use(express.static(path.join(__dirname, '../frontend/dist')));

app.listen(PORT, () => {
  console.log(`OpenClaw monitor listening on ${PORT}`);
});
