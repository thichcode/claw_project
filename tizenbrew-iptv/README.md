# Miso IPTV (TizenBrew app module)

Simple IPTV app module for TizenBrew.

## Features
- Load M3U playlist from URL
- Channel list + search
- Play HLS/HTTP streams in `<video>`
- TV remote friendly controls

## Controls
- Up/Down: move channel list
- Enter: play selected channel
- Left/Right: focus list/player panel
- Play/Pause: toggle playback
- Stop: stop stream
- Red key: focus URL input
- Green key: reload playlist

## Notes
- Works best with `m3u8`/HLS streams on Samsung Tizen TVs.
- Some codecs/streams may not be supported by TV hardware.

## Module structure
- `package.json` (TizenBrew app module metadata)
- `app/index.html`
- `app/style.css`
- `app/app.js`
- `service.js`
