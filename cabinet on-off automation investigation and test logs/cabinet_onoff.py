#!/usr/bin/env python3
"""Cabinet on/off over Modbus only — Route A.

The Watlow F4 has no run/stop register. What it has is a documented sentinel
on the setpoint itself (user manual, chapter 3, Static Set Point Control):

    "Setting the set point to Set Point Low Limit minus 1 (-1) will turn
     control Output 1 off and display the set point as off."

So OFF is F4 register 300 := (register 602) - 1, and ON is register 300 := the
wanted setpoint. The gateway owns that translation; this script only asks for a
state. See python modbus proof of concept and test logs/f4s_gateway.py and README.md section 16.

Command encoding is 0/1/2, not a boolean: holding registers come up as 0 after
a gateway restart, and an off==0 encoding would make every restart command a
stop before anyone had asked for one. 0 therefore means "no command".

CAUTION: this switches the F4's *control output*. Whether that also drops the
circulation fan depends on whether the fan hangs off the F4 output or off the
front-station latch relay, which is downstream of the controller and invisible
to Modbus (README.md sections 1 and 4). Confirm with test A1 before relying on
this as a full cabinet stop.
"""

import argparse
import sys

from pymodbus.client import ModbusTcpClient

GATEWAY_HOST = "10.1.6.17"
GATEWAY_PORT = 502
DEVICE_ID = 1            # gateway serves device id 1 ONLY (never 255)

REG_REQ_SP = 0           # write: setpoint applied when the cabinet is ON
REG_ONOFF_CMD = 5        # write: 0 = no command, 1 = off, 2 = on
REG_ONOFF_STATE = 6      # read:  0 = unknown, 1 = off, 2 = on
REG_SP_LOW = 7           # read:  F4 setpoint low limit, signed x10

CMD_NONE, CMD_OFF, CMD_ON = 0, 1, 2
STATE_NAMES = {0: "UNKNOWN", 1: "OFF", 2: "ON"}


def _u16_to_i16(value: int) -> int:
    return value - 65536 if value >= 32768 else value


def set_cabinet(run: bool, host: str = GATEWAY_HOST) -> None:
    """Command the cabinet on or off."""
    with ModbusTcpClient(host, port=GATEWAY_PORT) as c:
        c.write_register(REG_ONOFF_CMD, CMD_ON if run else CMD_OFF,
                         device_id=DEVICE_ID)


def cabinet_state(host: str = GATEWAY_HOST) -> int:
    """Return the observed state (CMD_OFF/CMD_ON encoding).

    Unlike a command echo this is derived from F4 register 300 as actually
    read back, so a setpoint changed at the keypad shows up here too.
    """
    with ModbusTcpClient(host, port=GATEWAY_PORT) as c:
        rr = c.read_holding_registers(REG_ONOFF_STATE, count=1,
                                      device_id=DEVICE_ID)
        return rr.registers[0]


def off_setpoint(host: str = GATEWAY_HOST) -> float:
    """The setpoint value the gateway writes to switch the output off."""
    with ModbusTcpClient(host, port=GATEWAY_PORT) as c:
        rr = c.read_holding_registers(REG_SP_LOW, count=1, device_id=DEVICE_ID)
        return (_u16_to_i16(rr.registers[0]) - 1) / 10.0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Switch the temperature cabinet on or off over Modbus "
                    "(Route A — no relays, no panel wiring)."
    )
    parser.add_argument("action", choices=["on", "off", "status"])
    parser.add_argument("--host", default=GATEWAY_HOST,
                        help=f"gateway IP (default {GATEWAY_HOST})")
    args = parser.parse_args()

    if args.action == "status":
        state = cabinet_state(args.host)
        print(f"Cabinet: {STATE_NAMES.get(state, state)}")
        print(f"OFF setpoint sentinel: {off_setpoint(args.host)}°C")
    else:
        run = args.action == "on"
        set_cabinet(run, args.host)
        print(f"Commanded cabinet {'ON' if run else 'OFF'}.")
        if run:
            print("ON restores the setpoint staged in register 0. If that "
                  "setpoint is out of range the command is refused and "
                  "register 4 reports status 4 (RANGE).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
