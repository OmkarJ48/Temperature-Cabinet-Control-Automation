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
| `test_temperature_swing_manager.py` | Unit tests (fake OPC client, no live PLC needed) |

## Running the tests

```bash
pip install pytest
pytest test_temperature_swing_manager.py -v
```

All 5 tests pass against a fake OPC client — no CODESYS connection required.

## Integration steps (in the main RnD repository)

1. Copy `config_temperature_swing.py` and `temperature_swing_manager.py` into
   `apps/dls/backend/automation/`.
2. Copy `websocket_temperature_swing.py` into `apps/dls/backend/` alongside
   the existing WebSocket broadcast module, and register
   `broadcast_temperature_swing_status()` as a background task on app
   startup (same pattern as the other status broadcasters).
3. Add three FastAPI routes:
   - `POST /api/temperature-swing/start` — accepts extreme temp, pressure
     mode, hold duration; builds a `TemperatureSwingConfig` and calls
     `TemperatureSwingManager.start_test()`.
   - `GET /api/temperature-swing/status` — calls `get_status()`.
   - `POST /api/temperature-swing/stop` — calls `stop_test()`.
4. Wire the manager's `opc_client` argument to the existing shared OPC UA
   client instance used by the rest of the DLS backend.
