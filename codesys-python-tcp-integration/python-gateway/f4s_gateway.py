#!/usr/bin/env python3
"""
f4s_gateway.py
Modbus TCP ↔ RTU Gateway for Watlow F4S Temperature Cabinet
Author: OJ (Omkar Joshi)
Purpose: Bridge CODESYS (TCP master) to Watlow F4S (RTU slave) over RS-232

Architecture:
  CODESYS (TCP master)  ←→  f4s_gateway (TCP slave + RTU master)  ←→  Watlow F4S (RTU slave)

TCP Register Map (holding registers):
  Reg 0: Requested new setpoint (x10, CODESYS → Python)
  Reg 1: Apply trigger (write 1, Python clears to 0)
  Reg 2: Current temperature (x10, Python → CODESYS, read-only)
  Reg 3: Current setpoint confirmed (x10, Python → CODESYS, read-only)
  Reg 4: Status/fault code (Python → CODESYS, read-only)
         0=OK, 2=WRITE_FAILED, 3=NOT_ACCEPTED, 4=RANGE, 5=COMMS

Values carry one implied decimal place: x10 integer (1300 = 130.0 °C).
"""

import logging
import time
import sys
from pymodbus.client import ModbusSerialClient as RTUClient
from pymodbus.server import StartAsyncTcpServer
from pymodbus.datastore import ModbusSlaveContext, ModbusServerContext
from pymodbus.datastore import ModbusSequentialDataBlock
import threading
import asyncio

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/f4s_gateway.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Gateway constants
SERIAL_PORT = '/dev/ttyWatlowF4S'
SERIAL_BAUD = 19200
RTU_SLAVE_ADDR = 1
TCP_PORT = 502
HEARTBEAT_INTERVAL = 1.0  # seconds
READ_TIMEOUT = 0.5  # seconds for write confirmation

# TCP register addresses
REG_REQUESTED_SETPOINT = 0
REG_APPLY_TRIGGER = 1
REG_CURRENT_TEMP = 2
REG_CURRENT_SETPOINT = 3
REG_STATUS = 4

# Status codes
STATUS_OK = 0
STATUS_WRITE_FAILED = 2
STATUS_NOT_ACCEPTED = 3
STATUS_RANGE_ERROR = 4
STATUS_COMMS_ERROR = 5

# F4S RTU register addresses
F4S_REG_TEMP = 100
F4S_REG_SETPOINT = 300


class F4SGateway:
    """Modbus TCP ↔ RTU gateway for Watlow F4S."""

    def __init__(self):
        self.rtu_client = None
        self.tcp_context = None
        self.running = False
        self.last_rtu_comms = time.time()
        self.write_in_progress = False
        self.write_target = None

    def connect_rtu(self):
        """Initialize RTU connection to F4S."""
        try:
            self.rtu_client = RTUClient(
                method='rtu',
                port=SERIAL_PORT,
                baudrate=SERIAL_BAUD,
                timeout=1.0,
                stopbits=1,
                bytesize=8,
                parity='N'
            )
            if self.rtu_client.connect():
                logger.info(f"RTU connection established: {SERIAL_PORT} @ {SERIAL_BAUD}")
                return True
            else:
                logger.error(f"Failed to connect RTU on {SERIAL_PORT}")
                return False
        except Exception as e:
            logger.error(f"RTU connection error: {e}")
            return False

    def read_f4s_register(self, reg_addr):
        """Read a single register from F4S (FC03)."""
        try:
            result = self.rtu_client.read_holding_registers(
                address=reg_addr,
                count=1,
                slave=RTU_SLAVE_ADDR
            )
            if result.isError():
                logger.warning(f"RTU read error at reg {reg_addr}: {result}")
                self.last_rtu_comms = time.time()
                return None
            self.last_rtu_comms = time.time()
            return result.registers[0] if result.registers else None
        except Exception as e:
            logger.error(f"RTU read exception at reg {reg_addr}: {e}")
            return None

    def write_f4s_register(self, reg_addr, value):
        """Write a single register to F4S (FC06)."""
        try:
            result = self.rtu_client.write_register(
                address=reg_addr,
                value=value,
                slave=RTU_SLAVE_ADDR
            )
            if result.isError():
                logger.warning(f"RTU write error at reg {reg_addr}, value {value}: {result}")
                self.last_rtu_comms = time.time()
                return False
            self.last_rtu_comms = time.time()
            logger.info(f"RTU write: reg{reg_addr} = {value}")
            return True
        except Exception as e:
            logger.error(f"RTU write exception at reg {reg_addr}, value {value}: {e}")
            return False

    def confirm_setpoint_write(self, written_value):
        """Read back setpoint within timeout to confirm F4S accepted it."""
        start = time.time()
        while (time.time() - start) < READ_TIMEOUT:
            read_back = self.read_f4s_register(F4S_REG_SETPOINT)
            if read_back is not None and read_back == written_value:
                logger.info(f"Setpoint write confirmed: reg{F4S_REG_SETPOINT} = {written_value}")
                return True
            time.sleep(0.1)
        logger.warning(f"Setpoint write NOT confirmed (timeout): expected {written_value}")
        return False

    def cyclic_task(self):
        """Main cyclic heartbeat: read F4S, update TCP, handle writes."""
        while self.running:
            try:
                # Read current temperature from F4S
                temp = self.read_f4s_register(F4S_REG_TEMP)
                if temp is not None:
                    self.tcp_context.setValues(3, REG_CURRENT_TEMP, [temp])
                    logger.debug(f"Temp: {temp/10.0}°C")

                # Read current setpoint from F4S
                current_sp = self.read_f4s_register(F4S_REG_SETPOINT)
                if current_sp is not None:
                    self.tcp_context.setValues(3, REG_CURRENT_SETPOINT, [current_sp])
                    logger.debug(f"Current SP: {current_sp/10.0}°C")

                # Check for apply trigger from CODESYS
                trigger_regs = self.tcp_context.getValues(3, REG_APPLY_TRIGGER, 1)
                if trigger_regs and trigger_regs[0]:
                    if not self.write_in_progress:
                        # Get the requested setpoint
                        sp_regs = self.tcp_context.getValues(3, REG_REQUESTED_SETPOINT, 1)
                        if sp_regs:
                            new_sp = sp_regs[0]
                            self.write_in_progress = True
                            self.write_target = new_sp

                            # Validate range (0–200 °C = 0–2000 x10)
                            if 0 <= new_sp <= 2000:
                                # Write to F4S
                                if self.write_f4s_register(F4S_REG_SETPOINT, new_sp):
                                    # Confirm write
                                    if self.confirm_setpoint_write(new_sp):
                                        self.tcp_context.setValues(3, REG_STATUS, [STATUS_OK])
                                        logger.info(f"Setpoint write SUCCESS: {new_sp/10.0}°C")
                                    else:
                                        self.tcp_context.setValues(3, REG_STATUS, [STATUS_NOT_ACCEPTED])
                                        logger.warning(f"F4S rejected setpoint: {new_sp/10.0}°C")
                                else:
                                    self.tcp_context.setValues(3, REG_STATUS, [STATUS_WRITE_FAILED])
                                    logger.error(f"Write failed to F4S")
                            else:
                                self.tcp_context.setValues(3, REG_STATUS, [STATUS_RANGE_ERROR])
                                logger.warning(f"Setpoint out of range: {new_sp/10.0}°C")

                            # Clear the trigger and write-in-progress
                            self.tcp_context.setValues(3, REG_APPLY_TRIGGER, [0])
                            self.write_in_progress = False

                # Check comms health
                time_since_comms = time.time() - self.last_rtu_comms
                if time_since_comms > 5.0:
                    self.tcp_context.setValues(3, REG_STATUS, [STATUS_COMMS_ERROR])
                    logger.warning("RTU communication timeout")

                time.sleep(HEARTBEAT_INTERVAL)

            except Exception as e:
                logger.error(f"Cyclic task error: {e}")
                time.sleep(HEARTBEAT_INTERVAL)

    def run(self):
        """Start the gateway."""
        logger.info("=== F4S Gateway Starting ===")

        # Connect to F4S
        if not self.connect_rtu():
            logger.error("Failed to connect to F4S. Exiting.")
            return False

        # Set up TCP slave context
        store = ModbusSlaveContext(
            di=ModbusSequentialDataBlock(0, [0] * 100),
            co=ModbusSequentialDataBlock(0, [0] * 100),
            hr=ModbusSequentialDataBlock(0, [0] * 100),
            ir=ModbusSequentialDataBlock(0, [0] * 100)
        )
        contexts = ModbusServerContext(stores={1: store}, single=False)
        self.tcp_context = contexts

        # Start cyclic task in background thread
        self.running = True
        cyclic_thread = threading.Thread(target=self.cyclic_task, daemon=True)
        cyclic_thread.start()
        logger.info(f"Cyclic task started (interval={HEARTBEAT_INTERVAL}s)")

        # Start TCP server
        logger.info(f"Starting TCP server on port {TCP_PORT}")
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            StartAsyncTcpServer(address=("0.0.0.0", TCP_PORT), context=contexts, loop=loop)
            loop.run_forever()
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            self.running = False
            if self.rtu_client:
                self.rtu_client.close()
        except Exception as e:
            logger.error(f"TCP server error: {e}")
            self.running = False
            if self.rtu_client:
                self.rtu_client.close()
            return False

        return True


if __name__ == '__main__':
    gateway = F4SGateway()
    gateway.run()
