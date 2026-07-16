#!/usr/bin/env python3
"""
F4S Modbus TCP<->RTU Gateway
============================
Owns the serial port to the Watlow F4S (RTU) and exposes a Modbus TCP slave
(server) so CODESYS can read/write the four required values over the network.

CODESYS is the TCP MASTER. This gateway is the TCP SLAVE + the RTU MASTER to F4S.
Only this process touches /dev/ttyWatlowF4S -> no serial contention.

  Stop the old CODESYS serial runtime hold before running (the serial Modbus
  device in CODESYS must be REMOVED/disabled; CODESYS now uses Modbus TCP).

TCP holding-register window (unit id 1), all setpoints/temps are x10 integers:
  reg 0  (RW)  requested setpoint  (CODESYS writes, e.g. 265 = 26.5 C)
  reg 1  (RW)  apply trigger       (CODESYS writes 1 to apply; gateway clears to 0)
  reg 2  (RO)  chamber temperature (gateway publishes, x10)
  reg 3  (RO)  confirmed setpoint  (gateway publishes read-back, x10)
  reg 4  (RO)  status/fault code   0=OK 2=WRITE_FAILED 3=NOT_ACCEPTED 4=RANGE 5=COMMS

Proven F4S params (this session): addr 1, 19200 8N1, reg100 temp, reg300 SP, /10.
"""

import logging
import threading
import time

from pymodbus.client import ModbusSerialClient
from pymodbus.server import StartTcpServer
from pymodbus.datastore import (
    ModbusSlaveContext,
    ModbusServerContext,
    ModbusSequentialDataBlock,
)

# ---- Configuration -------------------------------------------------------
SERIAL_PORT = "/dev/ttyWatlowF4S"     # stable udev symlink
BAUD        = 19200
SLAVE_ADDR  = 1                       # F4S Modbus address
REG_TEMP    = 100                     # F4S holding reg: chamber temp (x10)
REG_SP      = 300                     # F4S holding reg: setpoint SP1 (x10)
SP_MIN_C    = 0.0
SP_MAX_C    = 200.0
POLL_PERIOD = 1.0                     # seconds between F4S polls
TCP_HOST    = "0.0.0.0"               # bind all interfaces (Pi @ 10.1.6.17)
TCP_PORT    = 502                     # standard Modbus TCP (needs root/setcap)

# TCP register indices (into the holding-register block)
R_REQ, R_APPLY, R_TEMP, R_CONFSP, R_STATUS = 0, 1, 2, 3, 4

# Status codes (mirror CODESYS E_FaultCode intent)
ST_OK, ST_WRITE_FAILED, ST_NOT_ACCEPTED, ST_RANGE, ST_COMMS = 0, 2, 3, 4, 5

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler("f4s_gateway.log"), logging.StreamHandler()],
)
log = logging.getLogger("f4s_gw")

# ---- Shared TCP datastore ------------------------------------------------
# 8 holding registers, zero-based addressing.
_hr = ModbusSequentialDataBlock(0, [0] * 8)
_store = ModbusSlaveContext(hr=_hr, zero_mode=True)
_ctx = ModbusServerContext(slaves={SLAVE_ADDR: _store}, single=False)

# ---- Serial (RTU) client -------------------------------------------------
_rtu = ModbusSerialClient(
    port=SERIAL_PORT, baudrate=BAUD, parity="N",
    stopbits=1, bytesize=8, timeout=1,
)


def _get(idx):
    return _store.getValues(3, idx, count=1)[0]      # 3 = holding registers


def _set(idx, value):
    _store.setValues(3, idx, [int(value) & 0xFFFF])


def rtu_read(reg):
    """FC03 read of one holding register. Returns int or None."""
    try:
        rr = _rtu.read_holding_registers(address=reg, count=1, slave=SLAVE_ADDR)
        if rr.isError():
            log.warning("RTU read reg %d error: %s", reg, rr)
            return None
        return rr.registers[0]
    except Exception as exc:                          # noqa: BLE001
        log.error("RTU read reg %d exception: %s", reg, exc)
        return None


def rtu_write_sp(raw):
    """FC06 write of setpoint (x10 int). Returns True on comms success."""
    try:
        wr = _rtu.write_register(address=REG_SP, value=int(raw), slave=SLAVE_ADDR)
        if wr.isError():
            log.warning("RTU write SP error: %s", wr)
            return False
        return True
    except Exception as exc:                          # noqa: BLE001
        log.error("RTU write SP exception: %s", exc)
        return False


def poll_worker():
    """Owns the serial link. Publishes reads; services apply trigger."""
    if not _rtu.connect():
        log.error("Cannot open %s -- is it free? (stop any mbpoll / old CODESYS "
                  "serial hold). Exiting worker.", SERIAL_PORT)
        return
    log.info("Serial connected on %s @ %d 8N1", SERIAL_PORT, BAUD)

    while True:
        # --- publish current temperature + setpoint to TCP window ---
        t = rtu_read(REG_TEMP)
        s = rtu_read(REG_SP)
        if t is not None:
            _set(R_TEMP, t)
        if s is not None:
            _set(R_CONFSP, s)
        if t is None and s is None:
            _set(R_STATUS, ST_COMMS)                  # both reads failed -> comms fault

        # --- service apply trigger from CODESYS ---
        if _get(R_APPLY) == 1:
            req_raw = _get(R_REQ)                      # x10 int
            req_c = req_raw / 10.0
            log.info("Apply requested: %.1f C (raw %d)", req_c, req_raw)

            if not (SP_MIN_C <= req_c <= SP_MAX_C):
                log.warning("Requested %.1f C out of range %.0f-%.0f",
                            req_c, SP_MIN_C, SP_MAX_C)
                _set(R_STATUS, ST_RANGE)
            elif rtu_write_sp(req_raw):
                time.sleep(0.5)                       # let F4S apply
                back = rtu_read(REG_SP)
                if back == req_raw:
                    _set(R_CONFSP, back)
                    _set(R_STATUS, ST_OK)
                    log.info("CONFIRMED setpoint %.1f C", req_c)
                else:
                    _set(R_STATUS, ST_NOT_ACCEPTED)   # F4S in menu/profile mode
                    log.warning("NOT accepted: wrote %d, read back %s "
                                "(F4S on main run page?)", req_raw, back)
            else:
                _set(R_STATUS, ST_WRITE_FAILED)

            _set(R_APPLY, 0)                          # clear trigger (ack to CODESYS)

        time.sleep(POLL_PERIOD)


def main():
    threading.Thread(target=poll_worker, daemon=True).start()
    log.info("Modbus TCP slave starting on %s:%d (unit %d)",
             TCP_HOST, TCP_PORT, SLAVE_ADDR)
    StartTcpServer(context=_ctx, address=(TCP_HOST, TCP_PORT))


if __name__ == "__main__":
    main()
