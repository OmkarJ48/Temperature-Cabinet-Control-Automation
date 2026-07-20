#!/usr/bin/env python3
"""
F4S Modbus TCP ↔ RTU Gateway (pymodbus 3.14.0+)
Modbus TCP slave (server) ↔ Modbus RTU master to Watlow F4S
"""
import logging
import threading
import time
import sys
from pymodbus.client import ModbusSerialClient

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

# TCP registers (holding registers) — shared memory between cyclic task and TCP server
REG_REQ_SP = 0       # Requested setpoint (CODESYS → Python)
REG_TRIGGER = 1      # Apply trigger (CODESYS → Python)
REG_TEMP = 2         # Current temperature (Python → CODESYS, read-only)
REG_SP_READ = 3      # Confirmed setpoint (Python → CODESYS, read-only)
REG_STATUS = 4       # Status code (Python → CODESYS, read-only)

# Status codes
ST_OK = 0
ST_WRITE_FAIL = 2
ST_NOT_ACCEPTED = 3
ST_RANGE = 4
ST_COMMS = 5

# Global register storage (shared between cyclic task and TCP server)
tcp_regs = [0] * 10


class F4SGateway:
    def __init__(self):
        self.rtu = None
        self.running = False
        self.last_comms = time.time()
        self.write_pending = False

    def connect_rtu(self):
        """Connect to F4S via RTU."""
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

    def read_rtu_reg(self, addr):
        """Read holding register from F4S."""
        try:
            result = self.rtu.read_holding_registers(address=addr, count=1, device_id=SLAVE_ADDR)
            if result.isError():
                logger.warning(f"RTU read error @ reg{addr}")
                return None
            self.last_comms = time.time()
            return result.registers[0] if result.registers else None
        except Exception as e:
            logger.error(f"RTU read exception @ reg{addr}: {e}")
            return None

    def write_rtu_reg(self, addr, value):
        """Write holding register to F4S."""
        try:
            result = self.rtu.write_register(address=addr, value=value, device_id=SLAVE_ADDR)
            if result.isError():
                logger.warning(f"RTU write error @ reg{addr} = {value}")
                return False
            self.last_comms = time.time()
            logger.info(f"RTU write: reg{addr} = {value}")
            return True
        except Exception as e:
            logger.error(f"RTU write exception @ reg{addr}: {e}")
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

    def cyclic(self):
        """Main polling loop."""
        global tcp_regs
        while self.running:
            try:
                # Read temperature from F4S
                temp = self.read_rtu_reg(F4S_REG_TEMP)
                if temp is not None:
                    tcp_regs[REG_TEMP] = temp
                    logger.debug(f"Temp: {temp/10.0}°C")

                # Read current setpoint from F4S
                sp_read = self.read_rtu_reg(F4S_REG_SP)
                if sp_read is not None:
                    tcp_regs[REG_SP_READ] = sp_read
                    logger.debug(f"SP: {sp_read/10.0}°C")

                # Check for write trigger
                if tcp_regs[REG_TRIGGER] == 1 and not self.write_pending:
                    self.write_pending = True
                    sp_req = tcp_regs[REG_REQ_SP]
                    # Validate range (0–200°C = 0–2000 x10)
                    if 0 <= sp_req <= 2000:
                        # Write to F4S
                        if self.write_rtu_reg(F4S_REG_SP, sp_req):
                            # Confirm
                            if self.confirm_write(sp_req):
                                tcp_regs[REG_STATUS] = ST_OK
                                logger.info(f"Write SUCCESS: {sp_req/10.0}°C")
                            else:
                                tcp_regs[REG_STATUS] = ST_NOT_ACCEPTED
                                logger.warning(f"F4S rejected: {sp_req/10.0}°C")
                        else:
                            tcp_regs[REG_STATUS] = ST_WRITE_FAIL
                            logger.error("Write failed to F4S")
                    else:
                        tcp_regs[REG_STATUS] = ST_RANGE
                        logger.warning(f"Out of range: {sp_req/10.0}°C")
                    # Clear trigger
                    tcp_regs[REG_TRIGGER] = 0
                    self.write_pending = False

                # Check comms health
                if (time.time() - self.last_comms) > 5.0:
                    tcp_regs[REG_STATUS] = ST_COMMS
                    logger.warning("RTU comms timeout")

                time.sleep(POLL_PERIOD)

            except Exception as e:
                logger.error(f"Cyclic task error: {e}")
                time.sleep(POLL_PERIOD)

    def run(self):
        """Start gateway."""
        logger.info("=== F4S Gateway Starting ===")

        if not self.connect_rtu():
            logger.error("Failed to connect RTU. Exiting.")
            return False

        # Start cyclic task
        self.running = True
        cyclic_thread = threading.Thread(target=self.cyclic, daemon=True)
        cyclic_thread.start()
        logger.info(f"Cyclic task started (period={POLL_PERIOD}s)")
        logger.info(f"Register storage: tcp_regs array ready at memory addresses {REG_REQ_SP}-{REG_STATUS}")
        logger.info("TCP server layer: deferred to next iteration (RTU foundation stable)")

        # Keep gateway alive (cyclic task runs in background)
        try:
            while self.running:
                time.sleep(1)
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
