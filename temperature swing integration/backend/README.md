# Backend — Temperature Swing

Python-side manager and OPC UA node map for the Temperature Swing test.
Designed to plug into the existing DLS FastAPI backend's OPC UA client
(`apps/dls/backend/config.py` in the main RnD repository) — these files are
provider-agnostic and only assume an object exposing async `read`/`write`.

| File | Purpose |
|---|---|
| `config_temperature_swing.py` | OPC UA node ID map, rate/overshoot thresholds, pressure mode options |
| `temperature_swing_manager.py` | `TemperatureSwingManager` — start/poll/stop a test run |
| `websocket_temperature_swing.py` | Poll loop that broadcasts live status to connected HMI clients |
| `temperature_swing.py` | FastAPI `router` — the three REST routes plus the `/ws/temperature-swing` WebSocket, ready to drop into `apps/dls/backend/pages/` |
| `test_temperature_swing_manager.py` | Unit tests (fake OPC client, no live PLC needed) |

## Running the tests

```bash
pip install pytest
pytest test_temperature_swing_manager.py -v
```

All 5 tests pass against a fake OPC client — no CODESYS connection required.

## Integration steps (in the main RnD repository)

1. Copy `config_temperature_swing.py` and `temperature_swing_manager.py` into
   `apps/dls/backend/automation/` (update the import in
   `temperature_swing_manager.py` and `temperature_swing.py` accordingly,
   e.g. `from ..automation.temperature_swing_manager import ...`).
2. Copy `websocket_temperature_swing.py` and `temperature_swing.py` into
   `apps/dls/backend/pages/`, matching the other page routers
   (`live_trend.py`, `camera.py`).
3. `temperature_swing.py` already provides the three routes plus a
   `/ws/temperature-swing` WebSocket:
   - `POST /api/temperature-swing/start` — accepts extreme temp, pressure
     mode, hold duration; builds a `TemperatureSwingConfig` and calls
     `TemperatureSwingManager.start_test()`.
   - `GET /api/temperature-swing/status` — calls `get_status()`.
   - `POST /api/temperature-swing/stop` — calls `stop_test()`.
   Include its `router` on the app the same way the other page routers are
   included.
4. `temperature_swing.py`'s `get_manager()` wires the manager to the shared
   `opc` client via `_OpcNodeAdapter`, which assumes `opc.client` exposes a
   raw-node-id `get_node(id).get_value()/.set_value()` interface (the usual
   python-opcua/asyncua shape). Confirm this against the real `opc.py`
   wrapper and adjust the adapter if it differs.
5. Call `start_background_broadcaster()` once on app startup (e.g. from the
   app's `@app.on_event("startup")` handler) so WebSocket clients receive
   live updates while a test is active.
