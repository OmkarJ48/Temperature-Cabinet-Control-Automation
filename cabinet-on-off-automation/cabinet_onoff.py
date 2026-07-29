#!/usr/bin/env python3
"""Cabinet on/off remote command via the F4S Modbus TCP gateway (Path 2).

FUTURE REFERENCE — do not expect this to work against the deployed gateway yet.
The gateway currently serves registers 0-4 (setpoint control only). Registers
5 and 6 are the designed extension documented in cabinet-on-off-automation/
README.md section 10 and Part 7 of the handover document. Before first use:

  1. Extend f4s_gateway.py's register map from 5 to 7 registers:
       reg 5 (write) : on/off command   -- 0 = stop, 1 = run (level, NOT a
                                           self-clearing trigger like reg 1)
       reg 6 (read)  : command echo     -- what the gateway believes was asked
  2. Add CODESYS Modbus channel 5: Read Holding Registers (FC03), cyclic
     1000 ms, READ offset 16#0005, mapped to GVL_Modbus.wOnOffCmd (element
     row, type WORD -- same rules as channels 0-4).
  3. In PLC_PRG, feed the sequencer:
       GVL_HMI.xCabinetOnCmd := (GVL_Modbus.wOnOffCmd = 1) OR xLocalHmiRequest;
  4. Complete the physical wiring per README.md section 7a.

CODESYS remains the only actuator and owns the anti-short-cycle interlock
(5-minute minimum off time). This script only REQUESTS a state; a start
request inside the lockout window is deliberately delayed by the PLC.

CAUTION: a request is not a confirmation. Register 6 echoes what was asked
for. Proof that the cabinet is actually running is the fan, or the EL1409
run-feedback DI once fitted (README.md section 13, open item 4) -- never
this register.
"""

import argparse
import sys

from pymodbus.client import ModbusTcpClient

GATEWAY_HOST = "10.1.6.17"
GATEWAY_PORT = 502
DEVICE_ID = 1          # gateway serves device id 1 ONLY (never 255)
REG_ONOFF_CMD = 5      # write: 0 = stop, 1 = run
REG_ONOFF_ECHO = 6     # read: last requested state, echoed by the gateway


def set_cabinet(run: bool, host: str = GATEWAY_HOST) -> None:
    """Request cabinet run/stop. CODESYS performs the actuation."""
    with ModbusTcpClient(host, port=GATEWAY_PORT) as c:
        c.write_register(REG_ONOFF_CMD, 1 if run else 0, device_id=DEVICE_ID)


def cabinet_state(host: str = GATEWAY_HOST) -> bool:
    """Return the last REQUESTED state (True = run). Not proof of running."""
    with ModbusTcpClient(host, port=GATEWAY_PORT) as c:
        rr = c.read_holding_registers(REG_ONOFF_ECHO, count=1, device_id=DEVICE_ID)
        return rr.registers[0] == 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Request temperature-cabinet run/stop via the F4S gateway "
                    "(registers 5/6 -- see module docstring before first use)."
    )
    parser.add_argument("action", choices=["on", "off", "status"],
                        help="'on'/'off' write the request; 'status' reads the echo")
    parser.add_argument("--host", default=GATEWAY_HOST,
                        help=f"gateway IP (default {GATEWAY_HOST})")
    args = parser.parse_args()

    if args.action == "status":
        state = cabinet_state(args.host)
        print(f"Requested state: {'RUN' if state else 'STOP'} "
              "(echo only -- not proof the cabinet is running)")
    else:
        run = args.action == "on"
        set_cabinet(run, args.host)
        print(f"Requested cabinet {'RUN' if run else 'STOP'}. "
              "CODESYS actuates; starts may be held by the 5-minute "
              "anti-short-cycle lockout (watch GVL_HMI.tOffLockRemain).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
