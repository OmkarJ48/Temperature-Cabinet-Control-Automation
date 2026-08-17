"""Unit tests for TemperatureSwingConfig validation and manager status mapping.

Run with: pytest test_temperature_swing_manager.py
Uses a fake OPC client so no live CODESYS connection is required.
"""

from __future__ import annotations

import asyncio

import pytest

from temperature_swing_manager import (
    TemperatureSwingConfig,
    TemperatureSwingManager,
    TemperatureSwingState,
)


class FakeOpcClient:
    def __init__(self) -> None:
        self.written: dict[str, object] = {}
        self.values: dict[str, object] = {}

    async def write(self, node: str, value) -> None:
        self.written[node] = value

    async def read(self, node: str):
        return self.values.get(node)


def test_config_rejects_unknown_pressure_mode():
    with pytest.raises(ValueError):
        TemperatureSwingConfig(extreme_temp_c=-45.0, pressure_mode="200", hold_duration_min=10)


def test_config_rejects_non_positive_hold_time():
    with pytest.raises(ValueError):
        TemperatureSwingConfig(extreme_temp_c=-45.0, pressure_mode="50", hold_duration_min=0)


def test_config_accepts_valid_values():
    cfg = TemperatureSwingConfig(extreme_temp_c=85.0, pressure_mode="100", hold_duration_min=10)
    assert cfg.extreme_temp_c == 85.0


def test_start_test_writes_expected_nodes():
    client = FakeOpcClient()
    manager = TemperatureSwingManager(client)
    cfg = TemperatureSwingConfig(extreme_temp_c=-45.0, pressure_mode="50", hold_duration_min=10)

    asyncio.run(manager.start_test(cfg))

    assert client.written['ns=3;s="GVL"."rTemperatureSwing_Extreme"'] == -45.0
    assert client.written['ns=3;s="GVL"."rTemperatureSwing_PressureMode"'] == 50.0
    assert client.written['ns=3;s="GVL"."rTemperatureSwing_HoldTime"'] == 10
    assert client.written['ns=3;s="GVL"."xTemperatureSwing_Start"'] is True
    assert manager.is_active is True


def test_get_status_clears_active_flag_when_idle():
    client = FakeOpcClient()
    client.values['ns=3;s="GVL"."iTemperatureSwing_CurrentState"'] = int(
        TemperatureSwingState.IDLE
    )
    client.values['ns=3;s="GVL"."sTemperatureSwing_ErrorMessage"'] = ""
    for key in (
        'ns=3;s="GVL"."rBodyTemp_Current"',
        'ns=3;s="GVL"."rTemperatureSwing_Rate"',
        'ns=3;s="GVL"."rTemperatureSwing_Overshoot"',
        'ns=3;s="GVL"."rTemperatureSwing_MaxOvershoot"',
        'ns=3;s="GVL"."rTemperatureSwing_EstablishedPressure"',
        'ns=3;s="GVL"."iTemperatureSwing_HoldTimer"',
    ):
        client.values[key] = 0
    for key in (
        'ns=3;s="GVL"."xTemperatureSwing_RateCheckPassed"',
        'ns=3;s="GVL"."xTemperatureSwing_UsingFallbackChannel"',
        'ns=3;s="GVL"."xTemperatureSwing_OvershootExceeded"',
        'ns=3;s="GVL"."xTemperatureSwing_PressureReady"',
    ):
        client.values[key] = False

    manager = TemperatureSwingManager(client)
    manager._active = True  # simulate a test that was running

    status = asyncio.run(manager.get_status())

    assert status.state == TemperatureSwingState.IDLE
    assert manager.is_active is False
