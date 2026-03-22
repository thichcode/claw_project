const logList = document.getElementById('logList');
const statusEl = document.getElementById('status');
const filterText = document.getElementById('filterText');
const filterLevel = document.getElementById('filterLevel');
const toggleBtn = document.getElementById('toggleStream');
const downloadBtn = document.getElementById('downloadLogs');
let eventSource;
let paused = false;
let logs = [];

const render = () => {
  const textFilter = filterText.value.trim().toLowerCase();
  const levelFilter = filterLevel.value;
  logList.innerHTML = '';
  logs
    .filter((entry) => {
      if (filterLevel.value && entry.level !== levelFilter) return false;
      if (textFilter) return entry.message.toLowerCase().includes(textFilter) || entry.source.toLowerCase().includes(textFilter);
      return true;
    })
    .slice()
    .reverse()
    .forEach((entry) => {
      const row = document.createElement('div');
      row.className = `log-row ${paused ? 'paused' : ''}`;
      row.innerHTML = `
        <div>
          <div class="log-meta">
            <span>${entry.ts}</span>
            <span>${entry.source}</span>
            <span class="level-${entry.level}">${entry.level}</span>
          </div>
          <div class="log-message">${entry.message}</div>
        </div>
        <div>
          <small>${entry.ts}</small>
        </div>
      `;
      logList.appendChild(row);
    });
};

const connect = () => {
  if (eventSource) eventSource.close();
  eventSource = new EventSource('/api/logs/stream');
  statusEl.textContent = 'Connected';
  eventSource.onmessage = (event) => {
    const entry = JSON.parse(event.data);
    logs.push(entry);
    render();
  };
  eventSource.onerror = () => {
    statusEl.textContent = 'Disconnected – retrying…';
    eventSource.close();
    setTimeout(connect, 3000);
  };
};

filterText.addEventListener('input', render);
filterLevel.addEventListener('change', render);

toggleBtn.addEventListener('click', () => {
  if (!eventSource) return;
  paused = !paused;
  toggleBtn.textContent = paused ? 'Resume' : 'Pause';
  if (paused) eventSource.close(); else connect();
});

downloadBtn.addEventListener('click', () => {
  const text = logs.map((entry) => `${entry.ts} [${entry.level}] ${entry.source} ${entry.message}`).join('\n');
  const blob = new Blob([text], { type: 'text/plain' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `openclaw-logs-${Date.now()}.txt`;
  a.click();
  URL.revokeObjectURL(url);
});

connect();
