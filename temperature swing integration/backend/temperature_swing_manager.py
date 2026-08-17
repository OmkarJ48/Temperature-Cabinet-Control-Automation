"""Python-side manager for the Temperature Swing test.

Wraps the OPC UA node map in ``config_temperature_swing.py`` with a small
async interface: start a test, poll status, stop a test. This mirrors the
CODESYS-side state machine in ``codesys/FB_TemperatureSwing.st`` — it does
not run the test logic itself (CODESYS owns that), it only drives the start
handshake and surfaces live status for the HMI/API layer.

Expects an ``opc_client`` object exposing ``async def read(node_key)`` and
``async def write(node_key, value)``, matching the existing OPC UA client
used elsewhere in the DLS backend (see ``apps/dls/backend/config.py`` in the
main RnD repository for the client this was designed to plug into).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Optional

from config_temperature_swing import OPC_NODES_TEMPERATURE_SWING, PRESSURE_MODES


class TemperatureSwingState(IntEnum):
    IDLE = 0
    START = 1
    RAMP = 2
    MONITOR_RATE = 3
    APPROACH_EXTREME = 4
    VERIFY_EXTREME = 5
    STABILISE = 6
    OVERSHOOT_CHECK = 7
    HOLD_EXTREME = 8
    RETURN = 9
    RETURN_STABILISE = 10
    CYCLE_COMPLETE = 11


@dataclass
class TemperatureSwingConfig:
    extreme_temp_c: float
    pressure_mode: str          # "none", "50", "75", or "100"
    hold_duration_min: float

    def __post_init__(self) -> None:
        if self.pressure_mode not in PRESSURE_MODES:
            raise ValueError(
                f"pressure_mode must be one of {list(PRESSURE_MODES)}, got {self.pressure_mode!r}"
            )
        if self.hold_duration_min <= 0:
            raise ValueError("hold_duration_min must be positive")


@dataclass
class TemperatureSwingStatus:
    state: TemperatureSwingState
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


class TemperatureSwingManager:
    """Drives and observes a single Temperature Swing test run."""

    def __init__(self, opc_client) -> None:
        self._opc = opc_client
        self._active = False

    async def start_test(self, config: TemperatureSwingConfig) -> None:
        """Write operator configuration to CODESYS and trigger the start."""
        nodes = OPC_NODES_TEMPERATURE_SWING
        await self._opc.write(nodes["temperature_swing_extreme"], config.extreme_temp_c)
        await self._opc.write(
            nodes["temperature_swing_pressure_mode"], PRESSURE_MODES[config.pressure_mode]
        )
        await self._opc.write(nodes["temperature_swing_hold_time"], config.hold_duration_min)
        await self._opc.write(nodes["temperature_swing_start"], True)
        self._active = True

    async def get_status(self) -> TemperatureSwingStatus:
        """Poll current state from CODESYS."""
        nodes = OPC_NODES_TEMPERATURE_SWING
        state_val = await self._opc.read(nodes["temperature_swing_state"])
        error_message = await self._opc.read(nodes["temperature_swing_error_message"])

        status = TemperatureSwingStatus(
            state=TemperatureSwingState(state_val),
            current_temp_c=await self._opc.read(nodes["body_temp_current"]),
            rate_c_per_min=await self._opc.read(nodes["temperature_swing_rate"]),
            rate_passed=await self._opc.read(nodes["temperature_swing_rate_passed"]),
            using_fallback_channel=await self._opc.read(
                nodes["temperature_swing_using_fallback_channel"]
            ),
            overshoot_c=await self._opc.read(nodes["temperature_swing_overshoot"]),
            max_overshoot_c=await self._opc.read(nodes["temperature_swing_max_overshoot"]),
            overshoot_exceeded=await self._opc.read(
                nodes["temperature_swing_overshoot_exceeded"]
            ),
            pressure_ready=await self._opc.read(nodes["temperature_swing_pressure_ready"]),
            established_pressure_psi=await self._opc.read(
                nodes["temperature_swing_established_pressure"]
            ),
            hold_timer_sec=await self._opc.read(nodes["temperature_swing_hold_timer"]),
            error=error_message or None,
        )

        if status.state == TemperatureSwingState.IDLE:
            self._active = False

        return status

    async def stop_test(self) -> None:
        """Abort the running test."""
        await self._opc.write(OPC_NODES_TEMPERATURE_SWING["temperature_swing_stop"], True)
        self._active = False

    @property
    def is_active(self) -> bool:
        return self._active
