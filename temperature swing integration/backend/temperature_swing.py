"""FastAPI page router for the Temperature Swing test.

Follows the same conventions as the other DLS page routers (see
``apps/dls/backend/pages/live_trend.py`` and ``camera.py`` in the main RnD
repository): a module-level ``router = APIRouter()``, HTTPException-based
error handling (503 for PLC/connection issues, 500 for unexpected errors),
and a Pydantic request model for the POST body.

Drop this file into ``apps/dls/backend/pages/`` alongside the other page
routers, then:

1. Copy ``config_temperature_swing.py`` and ``temperature_swing_manager.py``
   into ``apps/dls/backend/automation/`` (update the import paths below to
   match, e.g. ``from ..automation.temperature_swing_manager import ...``).
2. Wire ``get_manager()`` below to the shared OPC UA client instance
   (``from ..opc import opc``) already used by the rest of the DLS backend.
3. Register ``router`` on the FastAPI app the same way the other page
   routers are included.
4. Call ``start_background_broadcaster()`` once on app startup (e.g. from a
   ``@app.on_event("startup")`` handler) so the WebSocket clients receive
   live updates.

The manager expects an async ``opc_client`` with ``read(node_id)`` /
``write(node_id, value)`` coroutines keyed by *raw* OPC UA node ID strings
(see ``OPC_NODES_TEMPERATURE_SWING`` in ``config_temperature_swing.py``).
The DLS backend's shared ``opc`` wrapper is synchronous and keyed by
friendly names (``opc.read("channel_readings")``), so ``_OpcNodeAdapter``
below bridges the two: it assumes ``opc`` exposes the underlying raw-node
client as ``opc.client`` (the common python-opcua/asyncua wrapper shape).
Adjust ``_OpcNodeAdapter`` if the actual ``opc.py`` wrapper differs.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional, Set

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from temperature_swing_manager import TemperatureSwingConfig, TemperatureSwingManager
from websocket_temperature_swing import broadcast_temperature_swing_status

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------- OPC bridge ----------

class _OpcNodeAdapter:
    """Bridges the sync, friendly-name DLS ``opc`` wrapper to the async,
    raw-node-id interface ``TemperatureSwingManager`` expects.
    """

    def __init__(self, opc_module) -> None:
        self._opc = opc_module

    async def read(self, node_id: str):
        return await asyncio.to_thread(self._read_sync, node_id)

    async def write(self, node_id: str, value) -> None:
        await asyncio.to_thread(self._write_sync, node_id, value)

    def _read_sync(self, node_id: str):
        return self._opc.client.get_node(node_id).get_value()

    def _write_sync(self, node_id: str, value) -> None:
        self._opc.client.get_node(node_id).set_value(value)


_manager: Optional[TemperatureSwingManager] = None


def get_manager() -> TemperatureSwingManager:
    """Lazily build the shared manager, wired to the DLS OPC UA client."""
    global _manager
    if _manager is None:
        from ..opc import opc  # deferred import: matches the other page routers

        if opc is None:
            raise HTTPException(status_code=503, detail="OPC UA server not initialized")
        _manager = TemperatureSwingManager(_OpcNodeAdapter(opc))
    return _manager


# ---------- WebSocket broadcast ----------

class _ConnectionManager:
    def __init__(self) -> None:
        self._connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.discard(websocket)

    async def broadcast(self, payload: dict) -> None:
        for websocket in list(self._connections):
            try:
                await websocket.send_json(payload)
            except Exception:
                self.disconnect(websocket)


_connections = _ConnectionManager()
_broadcaster_task: Optional[asyncio.Task] = None


def start_background_broadcaster() -> None:
    """Call once on app startup to begin polling CODESYS and pushing status."""
    global _broadcaster_task
    if _broadcaster_task is None:
        _broadcaster_task = asyncio.create_task(
            broadcast_temperature_swing_status(get_manager(), _connections.broadcast)
        )


@router.websocket("/ws/temperature-swing")
async def temperature_swing_ws(websocket: WebSocket) -> None:
    await _connections.connect(websocket)
    try:
        while True:
            # Client sends no messages; keep the connection open until it closes.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _connections.disconnect(websocket)


# ---------- Pydantic models ----------

class StartTemperatureSwingRequest(BaseModel):
    extreme_temp_c: float = Field(..., ge=-45.0, le=85.0)
    pressure_mode: str
    hold_duration_min: float = Field(..., gt=0)


class TemperatureSwingStatusResponse(BaseModel):
    state: str
    current_temp_c: float
    rate_c_per_min: float
    rate_passed: bool
    using_fallback_channel: bool
    overshoot_c: float
    max_overshoot_c: float
    overshoot_exceeded: bool
    pressure_ready: bool
    established_pressure_psi: float
    hold_timer_sec: int
    error: Optional[str] = None


# ---------- Routes ----------

@router.post("/api/temperature-swing/start")
async def start_temperature_swing(request: StartTemperatureSwingRequest):
    manager = get_manager()
    try:
        config = TemperatureSwingConfig(
            extreme_temp_c=request.extreme_temp_c,
            pressure_mode=request.pressure_mode,
            hold_duration_min=request.hold_duration_min,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        await manager.start_test(config)
    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=f"PLC Connection Error: {str(e)}")
    except Exception as e:
        logger.error(f"Temperature Swing start error: {e}")
        raise HTTPException(status_code=500, detail=f"PLC Data Error: {str(e)}")

    return {"status": "started"}


@router.get("/api/temperature-swing/status", response_model=TemperatureSwingStatusResponse)
async def get_temperature_swing_status():
    manager = get_manager()
    try:
        status = await manager.get_status()
    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=f"PLC Connection Error: {str(e)}")
    except Exception as e:
        logger.error(f"Temperature Swing status error: {e}")
        raise HTTPException(status_code=500, detail=f"PLC Data Error: {str(e)}")

    return TemperatureSwingStatusResponse(
        state=status.state.name,
        current_temp_c=status.current_temp_c,
        rate_c_per_min=status.rate_c_per_min,
        rate_passed=status.rate_passed,
        using_fallback_channel=status.using_fallback_channel,
        overshoot_c=status.overshoot_c,
        max_overshoot_c=status.max_overshoot_c,
        overshoot_exceeded=status.overshoot_exceeded,
        pressure_ready=status.pressure_ready,
        established_pressure_psi=status.established_pressure_psi,
        hold_timer_sec=status.hold_timer_sec,
        error=status.error,
    )


@router.post("/api/temperature-swing/stop")
async def stop_temperature_swing():
    manager = get_manager()
    try:
        await manager.stop_test()
    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=f"PLC Connection Error: {str(e)}")
    except Exception as e:
        logger.error(f"Temperature Swing stop error: {e}")
        raise HTTPException(status_code=500, detail=f"PLC Data Error: {str(e)}")

    return {"status": "stopped"}
