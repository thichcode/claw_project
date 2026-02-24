const playlistUrlEl = document.getElementById('playlistUrl');
const loadBtn = document.getElementById('loadBtn');
const searchInput = document.getElementById('searchInput');
const channelListEl = document.getElementById('channelList');
const nowPlayingEl = document.getElementById('nowPlaying');
const statusTextEl = document.getElementById('statusText');
const video = document.getElementById('video');

let channels = [];
let filtered = [];
let selectedIndex = 0;
let focusArea = 'list'; // list | player | controls
let hls = null;

const DEFAULT_PLAYLIST = localStorage.getItem('misoIptv:lastPlaylist') || 'https://raw.githubusercontent.com/thichcode/thichcode/refs/heads/main/fptplay.m3u';
playlistUrlEl.value = DEFAULT_PLAYLIST;

function setStatus(text) {
  statusTextEl.textContent = text;
}

function parseM3U(text) {
  const lines = text.split(/\r?\n/);
  const out = [];
  let currentMeta = null;

  for (const raw of lines) {
    const line = raw.trim();
    if (!line) continue;

    if (line.startsWith('#EXTINF')) {
      // Example: #EXTINF:-1 tvg-name="ABC" group-title="News",ABC Channel
      const namePart = line.includes(',') ? line.split(',').slice(1).join(',').trim() : 'Unknown';
      const groupMatch = line.match(/group-title="([^"]+)"/i);
      currentMeta = {
        name: namePart || 'Unknown',
        group: groupMatch ? groupMatch[1] : 'Other',
      };
      continue;
    }

    if (!line.startsWith('#')) {
      const item = {
        name: currentMeta?.name || line,
        group: currentMeta?.group || 'Other',
        url: line,
      };
      out.push(item);
      currentMeta = null;
    }
  }

  return out;
}

function renderList() {
  channelListEl.innerHTML = '';
  if (!filtered.length) {
    const li = document.createElement('li');
    li.textContent = 'No channels';
    channelListEl.appendChild(li);
    return;
  }

  filtered.forEach((ch, idx) => {
    const li = document.createElement('li');
    if (idx === selectedIndex) li.classList.add('active');
    li.innerHTML = `<div>${ch.name}</div><div class="meta">${ch.group}</div>`;
    li.onclick = () => {
      selectedIndex = idx;
      renderList();
      playSelected();
    };
    channelListEl.appendChild(li);
  });

  const active = channelListEl.querySelector('li.active');
  if (active) active.scrollIntoView({ block: 'nearest' });
}

function applySearch() {
  const q = searchInput.value.trim().toLowerCase();
  filtered = !q
    ? [...channels]
    : channels.filter(c => c.name.toLowerCase().includes(q) || c.group.toLowerCase().includes(q));

  if (selectedIndex >= filtered.length) selectedIndex = Math.max(0, filtered.length - 1);
  renderList();
}

function githubRawToJsdelivr(url) {
  try {
    const u = new URL(url);
    if (u.hostname !== 'raw.githubusercontent.com') return null;
    const parts = u.pathname.split('/').filter(Boolean);
    if (parts.length < 4) return null;
    const owner = parts[0];
    const repo = parts[1];
    const branch = parts[2];
    const filePath = parts.slice(3).join('/');
    return `https://cdn.jsdelivr.net/gh/${owner}/${repo}@${branch}/${filePath}`;
  } catch (_) {
    return null;
  }
}

async function fetchTextWithTimeout(url, timeoutMs = 15000) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(url, { signal: ctrl.signal, cache: 'no-store' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.text();
  } finally {
    clearTimeout(timer);
  }
}

async function loadPlaylist() {
  const url = playlistUrlEl.value.trim();
  if (!url) {
    setStatus('Missing playlist URL');
    return;
  }

  try {
    setStatus('Loading playlist...');
    let text;
    let usedUrl = url;

    try {
      text = await fetchTextWithTimeout(url, 15000);
    } catch (primaryErr) {
      const mirrorUrl = githubRawToJsdelivr(url);
      if (!mirrorUrl) throw primaryErr;

      setStatus('Primary URL failed, trying mirror...');
      text = await fetchTextWithTimeout(mirrorUrl, 15000);
      usedUrl = mirrorUrl;
    }

    channels = parseM3U(text);
    filtered = [...channels];
    selectedIndex = 0;
    renderList();

    localStorage.setItem('misoIptv:lastPlaylist', usedUrl);
    setStatus(`Loaded ${channels.length} channels`);
  } catch (err) {
    console.error(err);
    if (err?.name === 'AbortError') {
      setStatus('Load failed: timeout (network/TLS blocked?)');
      return;
    }
    setStatus(`Load failed: ${err.message || 'unknown error'}`);
  }
}

function playSelected() {
  if (!filtered.length) return;
  const ch = filtered[selectedIndex];
  if (!ch) return;

  nowPlayingEl.textContent = ch.name;
  setStatus('Buffering...');

  try {
    if (hls) {
      hls.destroy();
      hls = null;
    }

    const url = ch.url;
    const isHls = /\.m3u8($|\?)/i.test(url) || url.toLowerCase().includes('m3u8');

    if (isHls) {
      // Native HLS support (Safari / some TV runtimes)
      if (video.canPlayType('application/vnd.apple.mpegurl')) {
        video.src = url;
        video.play().catch(() => {});
        return;
      }

      // hls.js fallback (most desktop browsers)
      if (window.Hls && window.Hls.isSupported()) {
        hls = new window.Hls({ enableWorker: true });
        hls.loadSource(url);
        hls.attachMedia(video);
        hls.on(window.Hls.Events.MANIFEST_PARSED, () => {
          video.play().catch(() => {});
        });
        hls.on(window.Hls.Events.ERROR, (_, data) => {
          if (data?.fatal) {
            setStatus(`HLS fatal: ${data.type || 'unknown'}`);
          }
        });
        return;
      }

      setStatus('HLS not supported on this runtime');
      return;
    }

    // Non-HLS direct playback
    video.src = url;
    video.play().catch(() => {});
  } catch (err) {
    setStatus(`Play error: ${err.message}`);
  }
}

function moveSelection(delta) {
  if (!filtered.length) return;
  selectedIndex += delta;
  if (selectedIndex < 0) selectedIndex = 0;
  if (selectedIndex >= filtered.length) selectedIndex = filtered.length - 1;
  renderList();
}

video.addEventListener('playing', () => setStatus('Playing'));
video.addEventListener('pause', () => setStatus('Paused'));
video.addEventListener('waiting', () => setStatus('Buffering...'));
video.addEventListener('error', () => setStatus('Playback error'));

loadBtn.addEventListener('click', loadPlaylist);
searchInput.addEventListener('input', applySearch);

// Tizen key registration (best effort)
(function registerKeys() {
  try {
    if (window.tizen && tizen.tvinputdevice) {
      [
        'MediaPlay',
        'MediaPause',
        'MediaPlayPause',
        'MediaStop',
        'MediaFastForward',
        'MediaRewind',
        'ColorF0Red',
        'ColorF1Green',
        'ColorF2Yellow',
        'ColorF3Blue',
      ].forEach(k => {
        try { tizen.tvinputdevice.registerKey(k); } catch (_) {}
      });
    }
  } catch (_) {}
})();

window.addEventListener('keydown', (e) => {
  const key = e.key;
  const code = e.keyCode;

  // arrows + enter
  if (key === 'ArrowUp') {
    if (focusArea === 'list') moveSelection(-1);
    e.preventDefault();
    return;
  }
  if (key === 'ArrowDown') {
    if (focusArea === 'list') moveSelection(1);
    e.preventDefault();
    return;
  }
  if (key === 'ArrowLeft') {
    focusArea = 'list';
    e.preventDefault();
    return;
  }
  if (key === 'ArrowRight') {
    focusArea = 'player';
    e.preventDefault();
    return;
  }
  if (key === 'Enter') {
    if (focusArea === 'list') playSelected();
    e.preventDefault();
    return;
  }

  // media keys
  // Play/Pause codes vary by device, so check both key and keyCode
  if (key === 'MediaPlayPause' || code === 10252) {
    if (video.paused) video.play().catch(() => {});
    else video.pause();
    e.preventDefault();
    return;
  }
  if (key === 'MediaPlay' || code === 415) {
    video.play().catch(() => {});
    e.preventDefault();
    return;
  }
  if (key === 'MediaPause' || code === 19) {
    video.pause();
    e.preventDefault();
    return;
  }
  if (key === 'MediaStop' || code === 413) {
    video.pause();
    video.removeAttribute('src');
    video.load();
    setStatus('Stopped');
    e.preventDefault();
    return;
  }

  // Color keys
  if (key === 'ColorF0Red' || code === 403) {
    playlistUrlEl.focus();
    e.preventDefault();
    return;
  }
  if (key === 'ColorF1Green' || code === 404) {
    loadPlaylist();
    e.preventDefault();
    return;
  }
});

if (DEFAULT_PLAYLIST) {
  loadPlaylist();
}
