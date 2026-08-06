#!/usr/bin/env python3
"""
F4S Modbus TCP ↔ RTU Gateway (pymodbus==3.12.1 REQUIRED — see requirements.txt)
Modbus TCP slave (server) ↔ Modbus RTU master to Watlow F4S
"""
import logging
import threading
import time
import sys
import asyncio
from pymodbus.client import ModbusSerialClient
from pymodbus.server import StartAsyncTcpServer
from pymodbus.datastore import ModbusSparseDataBlock, ModbusServerContext, ModbusDeviceContext

import os
log_dir = os.path.expanduser('~/.f4s_gateway')
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, 'f4s_gateway.log')

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Configuration
SERIAL_PORT = "/dev/ttyWatlowF4S"
BAUD = 19200
SLAVE_ADDR = 1
TCP_HOST = "0.0.0.0"
TCP_PORT = 502
F4S_REG_TEMP = 100
F4S_REG_SP = 300
POLL_PERIOD = 1.0
READ_TIMEOUT = 0.5

# --- F4 registers used by the Modbus-only on/off route (Route A) -------------
# All addresses are from the Watlow Series F4 user manual, chapter 7
# ("Series F4 Modbus Registers"). docs/WatlowF4_UserManual.pdf.
#
# The controller has no "run/stop" register. What it has instead is a
# documented sentinel on the setpoint itself (manual chapter 3, Static Set
# Point Control):
#
#   "Setting the set point to Set Point Low Limit minus 1 (-1) will turn
#    control Output 1 off and display the set point as off."
#
# So OFF is reg 300 := (reg 602) - 1, and ON is reg 300 := the wanted
# setpoint. That reuses the exact write path this gateway already proves on
# every setpoint change — no new F4 behaviour, no new failure mode.
F4S_REG_SP_LOW_LIMIT = 602    # Set Point Low Limit, Analog Input 1 (r/w)
F4S_REG_OP_MODE = 200         # Operation Mode, Status (r)
F4S_REG_PROFILE_NOW = 4100    # Profile Number, Current Status (r) — 0 = none
F4S_REG_TERMINATE = 1217      # Terminate a Profile, Key Press Simulation (w, 1)

# A profile overrides the static setpoint, so writing the OFF sentinel while
# one is running would be ignored. Terminating first is what the manual says
# ends it: "the profile ends with all outputs off. The set point on the Main
# Page reads off." (chapter 3, To Terminate a Running/Holding Profile.)
F4S_TERMINATE_PROFILE = 1

# --- Setpoint range (x10, SIGNED) -------------------------------------------
# The cabinet range is -40..200 degC and PLC_PRG validates against exactly
# that. The gateway previously checked `0 <= sp_req <= 2000` against the RAW
# UNSIGNED register, so every negative setpoint arrived as its two's-complement
# value (-1.0 degC -> 65526), sailed past 2000, and was rejected as RANGE.
# Modbus registers are 16-bit with no signedness of their own; both ends must
# agree on the interpretation, and here it is signed.
SP_MIN_X10 = -400   # -40.0 degC
SP_MAX_X10 = 2000   # 200.0 degC


def u16_to_i16(value):
    """Reinterpret a raw holding-register word as a signed 16-bit integer."""
    return value - 65536 if value >= 32768 else value


def i16_to_u16(value):
    """Pack a signed 16-bit integer into the raw word placed on the wire."""
    return value + 65536 if value < 0 else value

# --- RTU link supervision ---------------------------------------------------
# The USB-RS232 adapter re-enumerates occasionally (kernel moves it between
# /dev/ttyUSBx nodes) while the service keeps running. The old file descriptor
# then raises OSError errno 5 (Input/output error) on every access. Reopening
# by the udev symlink re-resolves it to the node the adapter currently owns.
COMMS_TIMEOUT_S = 5.0            # no successful RTU exchange for this long -> status 5
RECONNECT_FAIL_THRESHOLD = 3     # consecutive failures that force a port reopen
RECONNECT_BACKOFF_START = 1.0    # first retry delay after a failed reopen
RECONNECT_BACKOFF_MAX = 10.0     # cap, so an unplugged cable doesn't spam the log

# TCP holding registers exposed to CODESYS
REG_REQ_SP = 0       # Requested setpoint (CODESYS → Python)
REG_TRIGGER = 1      # Apply trigger (CODESYS → Python)
REG_TEMP = 2         # Current temperature (Python → CODESYS, read-only)
REG_SP_READ = 3      # Confirmed setpoint (Python → CODESYS, read-only)
REG_STATUS = 4       # Status code (Python → CODESYS, read-only)
REG_ONOFF_CMD = 5    # On/off command (CODESYS → Python) — a level, not a trigger
REG_ONOFF_STATE = 6  # On/off state (Python → CODESYS, read-only)
REG_SP_LOW = 7       # F4 setpoint low limit, signed x10 (Python → CODESYS)
REG_PROFILE = 8      # Running profile number, 0 = none (Python → CODESYS)

# Status codes
ST_OK = 0
ST_WRITE_FAIL = 2
ST_NOT_ACCEPTED = 3
ST_RANGE = 4
ST_COMMS = 5
ST_OFF_STAGED = 6    # Setpoint accepted but held back — cabinet is commanded OFF

# On/off command and state codes.
#
# 0 is deliberately "no command", not "off". The holding registers initialise
# to 0 at start-up, so an off==0 encoding would have every gateway restart
# silently command the cabinet to stop before CODESYS had said anything.
CMD_NONE = 0
CMD_OFF = 1
CMD_ON = 2

STATE_UNKNOWN = 0    # not yet determined (no successful read since start-up)
STATE_OFF = 1        # F4 setpoint sits on the OFF sentinel
STATE_ON = 2         # F4 setpoint is a real setpoint; control output is live

# Modbus function code for holding registers (used by device.getValues/setValues)
FC_HOLDING = 3

# The device context is the single source of truth for both the RTU cyclic
# task and TCP clients (CODESYS). It must be built at module scope, before
# any thread starts, and ALL register access — from either side — must go
# through device.getValues()/setValues(), never the raw ModbusSparseDataBlock.
# (ModbusDeviceContext.getValues/setValues apply a +1 address offset before
# delegating to the raw block; bypassing the device context desyncs the
# addressing between the cyclic task and the TCP protocol layer.)
hr_block = ModbusSparseDataBlock({i: 0 for i in range(10)})
device = ModbusDeviceContext(
    di=ModbusSparseDataBlock({i: 0 for i in range(10)}),
    co=ModbusSparseDataBlock({i: 0 for i in range(10)}),
    ir=ModbusSparseDataBlock({i: 0 for i in range(10)}),
    hr=hr_block
)
server_context = ModbusServerContext(devices={1: device}, single=False)
hr_lock = threading.Lock()  # Guards device access from cyclic task vs TCP server


class F4SGateway:
    def __init__(self):
        self.rtu = None
        self.running = False
        # 0.0 (not now()) so the link counts as down until a read actually
        # succeeds — a gateway that never reached the F4S must not report OK.
        self.last_comms = 0.0
        self.write_pending = False
        # Link supervision state
        self.consecutive_failures = 0
        self.port_dead = False          # an OSError was seen; the fd is unusable
        self.reconnect_backoff = RECONNECT_BACKOFF_START
        self.next_reconnect_at = 0.0
        self.comms_healthy = None       # tri-state, so transitions log once
        # On/off (Route A) state
        self.off_sentinel = None        # (SP low limit - 1), x10; None until read
        self.onoff_state = STATE_UNKNOWN

    def connect_rtu(self):
        """(Re)open the serial port.

        Closes any existing client first so the stale file descriptor is
        released, then builds a *fresh* client. Opening by the udev symlink
        (not a fixed ttyUSBx) is what makes this pick up the adapter's current
        node after a re-enumeration.
        """
        if self.rtu is not None:
            try:
                self.rtu.close()
            except Exception as e:
                logger.debug(f"Ignoring error while closing stale RTU client: {e}")
            self.rtu = None

        try:
            self.rtu = ModbusSerialClient(
                port=SERIAL_PORT,
                baudrate=BAUD,
                timeout=1,
                bytesize=8,
                stopbits=1,
                parity="N"
            )
            if self.rtu.connect():
                logger.info(f"RTU connected: {SERIAL_PORT} @ {BAUD}")
                return True
            else:
                logger.error(f"RTU connect failed: {SERIAL_PORT}")
                return False
        except Exception as e:
            logger.error(f"RTU exception: {e}")
            return False

    def _note_success(self):
        """A real exchange with the F4S completed — the link is healthy."""
        self.last_comms = time.time()
        self.consecutive_failures = 0
        self.port_dead = False
        self.reconnect_backoff = RECONNECT_BACKOFF_START
        self.next_reconnect_at = 0.0

    def _note_failure(self, port_dead=False):
        """Record a failed exchange.

        port_dead=True means the file descriptor itself is unusable (OSError,
        e.g. errno 5 after a re-enumeration) and the port must be reopened.
        A protocol-level failure (isError(): timeout, bad CRC, exception
        response) leaves the fd valid, so it only increments the counter —
        reopening the port on every unanswered poll would thrash it.
        """
        self.consecutive_failures += 1
        if port_dead:
            self.port_dead = True

    def ensure_rtu(self):
        """Reopen the serial port when the current handle looks unusable.

        Triggers on either a dead fd or RECONNECT_FAIL_THRESHOLD consecutive
        failures — the latter covers a port that stops answering without ever
        raising. Backoff grows per attempt and is reset only by a genuinely
        successful read, so an unplugged cable settles at one quiet retry
        every RECONNECT_BACKOFF_MAX seconds while recovery stays near-instant.
        """
        needs_reopen = (
            self.port_dead
            or self.consecutive_failures >= RECONNECT_FAIL_THRESHOLD
        )
        if not needs_reopen:
            return

        now = time.time()
        if now < self.next_reconnect_at:
            return

        logger.warning(
            f"Reopening {SERIAL_PORT} "
            f"(consecutive failures={self.consecutive_failures}, port_dead={self.port_dead})"
        )
        # Schedule the next attempt before trying, so every path is rate-limited.
        self.next_reconnect_at = now + self.reconnect_backoff
        self.reconnect_backoff = min(self.reconnect_backoff * 2, RECONNECT_BACKOFF_MAX)

        if self.connect_rtu():
            # Port opened, but recovery is only proven by a successful read;
            # _note_success() (next poll) is what clears the failure state.
            self.port_dead = False
            logger.info(f"{SERIAL_PORT} reopened — awaiting first successful read")
        else:
            logger.warning(
                f"Reopen failed; next attempt in {self.reconnect_backoff:.0f}s "
                f"(adapter unplugged?)"
            )

    def read_rtu_reg(self, addr):
        """Read holding register from F4S."""
        if self.rtu is None:
            self._note_failure(port_dead=True)
            return None
        try:
            result = self.rtu.read_holding_registers(address=addr, count=1, device_id=SLAVE_ADDR)
            if result.isError():
                logger.warning(f"RTU read error @ reg{addr}")
                self._note_failure()
                return None
            self._note_success()
            return result.registers[0] if result.registers else None
        except OSError as e:
            # errno 5 (Input/output error) lands here when the adapter has
            # re-enumerated and this fd now points at a node that is gone.
            # pyserial's SerialException is an OSError subclass.
            logger.error(f"RTU read I/O error @ reg{addr}: {e}")
            self._note_failure(port_dead=True)
            return None
        except Exception as e:
            logger.error(f"RTU read exception @ reg{addr}: {e}")
            self._note_failure()
            return None

    def write_rtu_reg(self, addr, value):
        """Write holding register to F4S."""
        if self.rtu is None:
            self._note_failure(port_dead=True)
            return False
        try:
            result = self.rtu.write_register(address=addr, value=value, device_id=SLAVE_ADDR)
            if result.isError():
                logger.warning(f"RTU write error @ reg{addr} = {value}")
                self._note_failure()
                return False
            self._note_success()
            logger.info(f"RTU write: reg{addr} = {value}")
            return True
        except OSError as e:
            logger.error(f"RTU write I/O error @ reg{addr}: {e}")
            self._note_failure(port_dead=True)
            return False
        except Exception as e:
            logger.error(f"RTU write exception @ reg{addr}: {e}")
            self._note_failure()
            return False

    def confirm_write(self, written_val):
        """Read back after write to confirm F4S accepted it."""
        start = time.time()
        while (time.time() - start) < READ_TIMEOUT:
            read_back = self.read_rtu_reg(F4S_REG_SP)
            if read_back is not None and read_back == written_val:
                logger.info(f"Setpoint write confirmed: {written_val}")
                return True
            time.sleep(0.05)
        logger.warning(f"Setpoint write NOT confirmed (timeout): expected {written_val}")
        return False

    def ensure_off_sentinel(self):
        """Learn the OFF setpoint from the controller itself.

        Read once and cached. Hard-coding it would be wrong: the low limit
        follows the configured sensor and can be changed on the Setup Page,
        and a stale sentinel would either fail to switch the output off or
        land inside the usable range and quietly become a real setpoint.
        Re-read is cheap; getting it wrong is not.
        """
        if self.off_sentinel is not None:
            return True

        raw = self.read_rtu_reg(F4S_REG_SP_LOW_LIMIT)
        if raw is None:
            return False

        low_limit = u16_to_i16(raw)
        self.off_sentinel = low_limit - 1
        with hr_lock:
            device.setValues(FC_HOLDING, REG_SP_LOW, [i16_to_u16(low_limit)])
        logger.info(
            f"F4 setpoint low limit = {low_limit/10.0}°C -> "
            f"OFF sentinel = {self.off_sentinel/10.0}°C (reg {F4S_REG_SP} := "
            f"{self.off_sentinel})"
        )
        return True

    def apply_off(self):
        """Command the F4 to switch its control output off.

        A running profile owns the setpoint, so it has to be terminated first
        or the sentinel write lands on a value the profile immediately
        overwrites. Terminating already leaves all outputs off, so the
        sentinel write after it is what makes the state *stick* once the
        profile is gone.
        """
        profile = self.read_rtu_reg(F4S_REG_PROFILE_NOW)
        if profile is not None:
            with hr_lock:
                device.setValues(FC_HOLDING, REG_PROFILE, [profile])
            if profile != 0:
                logger.info(f"Profile {profile} running — terminating before OFF")
                self.write_rtu_reg(F4S_REG_TERMINATE, F4S_TERMINATE_PROFILE)

        return self.write_rtu_reg(F4S_REG_SP, i16_to_u16(self.off_sentinel))

    def apply_on(self, sp_req_raw):
        """Restore a real setpoint, which is what turns the control output on.

        The setpoint used is whatever CODESYS currently has staged in
        REG_REQ_SP. If that is out of range — or is itself the OFF sentinel,
        which would make ON a no-op — the command is refused rather than
        guessed at.
        """
        sp_signed = u16_to_i16(sp_req_raw)
        if not (SP_MIN_X10 <= sp_signed <= SP_MAX_X10):
            logger.warning(
                f"ON refused: staged setpoint {sp_signed/10.0}°C is out of range"
            )
            with hr_lock:
                device.setValues(FC_HOLDING, REG_STATUS, [ST_RANGE])
            return False
        if sp_signed == self.off_sentinel:
            logger.warning("ON refused: staged setpoint is the OFF sentinel")
            with hr_lock:
                device.setValues(FC_HOLDING, REG_STATUS, [ST_RANGE])
            return False

        return self.write_rtu_reg(F4S_REG_SP, sp_req_raw)

    def service_onoff(self, sp_read, sp_req_raw):
        """Drive the cabinet on/off from REG_ONOFF_CMD.

        `sp_read` is this pass's reading of F4 reg 300, so the state echo is
        derived from what the controller actually holds rather than from what
        was last commanded — a setpoint changed at the keypad shows up here
        too. Writes happen only when the observed state disagrees with the
        command, so a steady command costs nothing on the RTU link.
        """
        if not self.ensure_off_sentinel():
            return

        if sp_read is not None:
            observed = (
                STATE_OFF if u16_to_i16(sp_read) == self.off_sentinel else STATE_ON
            )
            if observed != self.onoff_state:
                logger.info(
                    f"Cabinet state -> {'OFF' if observed == STATE_OFF else 'ON'}"
                )
            self.onoff_state = observed
            with hr_lock:
                device.setValues(FC_HOLDING, REG_ONOFF_STATE, [self.onoff_state])

        with hr_lock:
            cmd = device.getValues(FC_HOLDING, REG_ONOFF_CMD, 1)[0]

        if cmd == CMD_NONE or self.onoff_state == STATE_UNKNOWN:
            return

        # A successful write updates the cached state immediately. Waiting for
        # the next poll to observe it would make this branch fire a second,
        # identical write in the meantime.
        if cmd == CMD_OFF and self.onoff_state != STATE_OFF:
            logger.info("Command OFF — writing sentinel setpoint")
            if self.apply_off():
                self.onoff_state = STATE_OFF
                with hr_lock:
                    device.setValues(FC_HOLDING, REG_ONOFF_STATE, [STATE_OFF])
                    device.setValues(FC_HOLDING, REG_STATUS, [ST_OK])
            else:
                with hr_lock:
                    device.setValues(FC_HOLDING, REG_STATUS, [ST_WRITE_FAIL])
        elif cmd == CMD_ON and self.onoff_state != STATE_ON:
            logger.info("Command ON — restoring staged setpoint")
            if self.apply_on(sp_req_raw):
                self.onoff_state = STATE_ON
                with hr_lock:
                    device.setValues(FC_HOLDING, REG_ONOFF_STATE, [STATE_ON])
                    device.setValues(FC_HOLDING, REG_STATUS, [ST_OK])
        elif cmd not in (CMD_OFF, CMD_ON):
            logger.warning(f"Unknown on/off command {cmd} — ignored")

    def cyclic(self):
        """Main polling loop. Reads/writes through the device context —
        the same accessor the TCP server uses to serve CODESYS requests."""
        while self.running:
            try:
                # Reopen the port first if the last pass showed it dead, so the
                # reads below run against a live handle instead of failing again.
                self.ensure_rtu()

                # Read temperature from F4S
                temp = self.read_rtu_reg(F4S_REG_TEMP)
                if temp is not None:
                    with hr_lock:
                        device.setValues(FC_HOLDING, REG_TEMP, [temp])
                    logger.debug(f"Temp: {u16_to_i16(temp)/10.0}°C")

                # Read current setpoint from F4S
                sp_read = self.read_rtu_reg(F4S_REG_SP)
                if sp_read is not None:
                    with hr_lock:
                        device.setValues(FC_HOLDING, REG_SP_READ, [sp_read])
                    logger.debug(f"SP: {u16_to_i16(sp_read)/10.0}°C")

                # Check for write trigger (set by CODESYS/TCP client over TCP)
                with hr_lock:
                    trigger = device.getValues(FC_HOLDING, REG_TRIGGER, 1)[0]
                    sp_req = device.getValues(FC_HOLDING, REG_REQ_SP, 1)[0]

                with hr_lock:
                    onoff_cmd = device.getValues(FC_HOLDING, REG_ONOFF_CMD, 1)[0]

                if trigger == 1 and not self.write_pending:
                    self.write_pending = True
                    # Validate range (-40..200 degC = -400..2000 x10), signed.
                    sp_signed = u16_to_i16(sp_req)
                    if onoff_cmd == CMD_OFF:
                        # The cabinet is commanded off, and off *is* a setpoint
                        # value here. Pushing a normal setpoint through now
                        # would silently restart the cabinet, so the request is
                        # held in REG_REQ_SP and applied on the next ON instead.
                        # ST_OFF_STAGED tells CODESYS the difference between
                        # "written" and "will be written when you turn it on".
                        with hr_lock:
                            device.setValues(FC_HOLDING, REG_STATUS, [ST_OFF_STAGED])
                        logger.info(
                            f"Setpoint {sp_signed/10.0}°C staged — cabinet commanded OFF"
                        )
                    elif SP_MIN_X10 <= sp_signed <= SP_MAX_X10:
                        # Write to F4S. sp_req is already the correct wire word
                        # (the signed value packed by CODESYS); pass it through
                        # unchanged so no round-trip can perturb the bit pattern.
                        if self.write_rtu_reg(F4S_REG_SP, sp_req):
                            # Confirm
                            if self.confirm_write(sp_req):
                                with hr_lock:
                                    device.setValues(FC_HOLDING, REG_STATUS, [ST_OK])
                                logger.info(f"Write SUCCESS: {sp_signed/10.0}°C")
                            else:
                                with hr_lock:
                                    device.setValues(FC_HOLDING, REG_STATUS, [ST_NOT_ACCEPTED])
                                logger.warning(f"F4S rejected: {sp_signed/10.0}°C")
                        else:
                            with hr_lock:
                                device.setValues(FC_HOLDING, REG_STATUS, [ST_WRITE_FAIL])
                            logger.error("Write failed to F4S")
                    else:
                        with hr_lock:
                            device.setValues(FC_HOLDING, REG_STATUS, [ST_RANGE])
                        logger.warning(f"Out of range: {sp_signed/10.0}°C")
                    # Clear trigger
                    with hr_lock:
                        device.setValues(FC_HOLDING, REG_TRIGGER, [0])
                    self.write_pending = False

                # Run the on/off service after the setpoint path so the two
                # never write reg 300 in the same pass. sp_read is this pass's
                # reading, i.e. the state echo trails a write by one poll —
                # acceptable, and it is why the echo is authoritative about
                # the controller rather than about the last command.
                self.service_onoff(sp_read, sp_req)

                # Check comms health.
                # COMMS is latched while the link is down AND cleared again on
                # recovery. Without the clear, REG_STATUS stayed at 5 forever
                # once it had ever tripped, which parks PLC_PRG's state machine
                # in FAULTED long after RTU comms are back. Only a 5 is cleared
                # here — a real WRITE_FAILED/NOT_ACCEPTED/RANGE result must
                # survive for CODESYS to act on.
                comms_ok = (time.time() - self.last_comms) <= COMMS_TIMEOUT_S
                if not comms_ok:
                    with hr_lock:
                        device.setValues(FC_HOLDING, REG_STATUS, [ST_COMMS])
                    if self.comms_healthy is not False:
                        logger.warning("RTU comms timeout — status -> 5 (COMMS)")
                    self.comms_healthy = False
                else:
                    if self.comms_healthy is False:
                        with hr_lock:
                            if device.getValues(FC_HOLDING, REG_STATUS, 1)[0] == ST_COMMS:
                                device.setValues(FC_HOLDING, REG_STATUS, [ST_OK])
                        logger.info("RTU comms recovered — status 5 -> 0 (OK)")
                    self.comms_healthy = True

                time.sleep(POLL_PERIOD)

            except Exception as e:
                logger.error(f"Cyclic task error: {e}")
                time.sleep(POLL_PERIOD)

    def run(self):
        """Start gateway."""
        logger.info("=== F4S Gateway Starting ===")

        # A missing adapter at boot is no longer fatal: come up anyway so the
        # TCP server is reachable and CODESYS sees status 5 (COMMS) instead of
        # a refused connection. ensure_rtu() keeps retrying with backoff and
        # the gateway heals itself the moment the adapter appears.
        if not self.connect_rtu():
            logger.warning(
                f"RTU not available at startup ({SERIAL_PORT}); "
                f"serving TCP and retrying in background"
            )
            self.port_dead = True

        # Start cyclic task
        self.running = True
        cyclic_thread = threading.Thread(target=self.cyclic, daemon=True)
        cyclic_thread.start()
        logger.info(f"Cyclic task started (period={POLL_PERIOD}s)")

        # Start TCP server in background thread with asyncio event loop
        def run_tcp_server():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                logger.info(f"Starting TCP server on {TCP_HOST}:{TCP_PORT}")
                loop.run_until_complete(
                    StartAsyncTcpServer(context=server_context, address=(TCP_HOST, TCP_PORT))
                )
            except Exception as e:
                logger.error(f"TCP server error: {e}")
                self.running = False

        tcp_thread = threading.Thread(target=run_tcp_server, daemon=True)
        tcp_thread.start()
        time.sleep(1)  # Give TCP server time to start
        logger.info(f"TCP server ready on {TCP_HOST}:{TCP_PORT}")

        # Keep gateway alive (cyclic task and TCP server run in background threads)
        try:
            while self.running:
                time.sleep(0.5)
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            self.running = False
            if self.rtu:
                self.rtu.close()
            return True

        return True


if __name__ == '__main__':
    gateway = F4SGateway()
    gateway.run()
