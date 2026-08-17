# Frontend — Temperature Swing

HMI pages for the Temperature Swing test, designed to load into the WebVisu
via `VisuFbWebBrowser` alongside the existing pages (`_02_Trend`,
`_04_Details`, `_05_Automation`, etc.) in the main RnD repository.

| File | Purpose |
|---|---|
| `start_dialog_temperature_swing.html` | Operator start dialog — extreme temp, pressure mode, hold duration |
| `temperature_swing_progress.html` | Live progress display — state, rate, overshoot, pressure, hold countdown |
| `temperature_swing_client.js` | Shared client: REST calls to start/stop, WebSocket subscription for live updates |

## Dependencies

- `../shared/frontend_assets/main.css` — reuses the existing centralized
  styling from the main RnD repository (`shared/frontend_assets/main.css`).
  Path assumes these files are copied into
  `apps/dls/frontend/pages/temperature_swing/`; adjust the relative
  `../shared/...` path if placed elsewhere.
- Backend routes and WebSocket endpoint described in `../backend/README.md`
  (`/api/temperature-swing/{start,stop}`, `/ws/temperature-swing`).

## Integration steps (in the main RnD repository)

1. Copy all three files into `apps/dls/frontend/pages/`.
2. Add a menu entry in `_05_Automation` linking to
   `start_dialog_temperature_swing.html`.
3. Confirm `main.css` path resolves correctly from the new location.
4. Verify the FastAPI backend exposes `/ws/temperature-swing` (see
   `../backend/websocket_temperature_swing.py`) before testing the progress
   page — without it the page will show "—" placeholders and silently retry
   the WebSocket connection every 2 s.

## Manual verification checklist

- [ ] Start dialog rejects extreme temperature outside -45..85°C
- [ ] Start dialog rejects hold duration outside 5..60 min
- [ ] Start dialog POSTs to `/api/temperature-swing/start` and navigates to
      the progress page on success
- [ ] Progress page connects to the WebSocket and updates state/rate/overshoot
      live
- [ ] Stop button POSTs to `/api/temperature-swing/stop` and returns to
      `_05_Automation.html`
- [ ] Fallback-channel row appears only when `using_fallback_channel` is true
