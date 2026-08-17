"""Real-time WebSocket status broadcast for the Temperature Swing progress page.

Plugs into the existing DLS WebSocket broadcast infrastructure — this module
provides the Temperature Swing–specific poll/broadcast loop; it expects a
``broadcast(payload: dict)`` coroutine from the host app (matching the
pattern used by the other status broadcasters in the main RnD backend) and a
``TemperatureSwingManager`` instance to poll.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

from temperature_swing_manager import TemperatureSwingManager, TemperatureSwingState

logger = logging.getLogger(__name__)

POLL_INTERVAL_SEC = 1.0


async def broadcast_temperature_swing_status(
    manager: TemperatureSwingManager,
    broadcast: Callable[[dict], Awaitable[None]],
    poll_interval_sec: float = POLL_INTERVAL_SEC,
) -> None:
    """Poll CODESYS via ``manager`` and push status to all connected HMI clients.

    Runs until cancelled. Only broadcasts while a test is active to avoid
    flooding idle HMI clients with no-op updates.
    """
    while True:
        try:
            if manager.is_active:
                status = await manager.get_status()
                await broadcast(
                    {
                        "type": "temperature_swing_update",
                        "state": status.state.name,
                        "current_temp_c": status.current_temp_c,
                        "rate_c_per_min": status.rate_c_per_min,
                        "rate_passed": status.rate_passed,
                        "using_fallback_channel": status.using_fallback_channel,
                        "overshoot_c": status.overshoot_c,
                        "max_overshoot_c": status.max_overshoot_c,
                        "overshoot_exceeded": status.overshoot_exceeded,
                        "pressure_ready": status.pressure_ready,
                        "established_pressure_psi": status.established_pressure_psi,
                        "hold_timer_sec": status.hold_timer_sec,
                        "error": status.error,
                    }
                )
                if status.state == TemperatureSwingState.CYCLE_COMPLETE:
                    await broadcast({"type": "temperature_swing_complete"})
        except Exception:
            logger.exception("Temperature Swing status broadcast failed")

        await asyncio.sleep(poll_interval_sec)
