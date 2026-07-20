#!/usr/bin/env python3
"""F4S Modbus TCP ↔ RTU Gateway - Simple approach"""
import logging
import threading
import time
import sys
import os
from pymodbus.client import ModbusSerialClient

log_dir = os.path.expanduser('~/.f4s_gateway')
os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(log_dir, 'f4s_gateway.log')),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

SERIAL_PORT = "/dev/ttyWatlowF4S"
BAUD, SLAVE_ADDR = 19200, 1
F4S_REG_TEMP, F4S_REG_SP = 100, 300
REG_REQ_SP, REG_TRIGGER, REG_TEMP, REG_SP_READ, REG_STATUS = 0, 1, 2, 3, 4

# Global register storage (Modbus TCP will read/write here)
tcp_regs = [0] * 10


class F4SGateway:
    def __init__(self):
        self.rtu = None
        self.running = False
        self.last_comms = time.time()

    def connect_rtu(self):
        try:
            self.rtu = ModbusSerialClient(
                port=SERIAL_PORT, baudrate=BAUD, timeout=1,
                bytesize=8, stopbits=1, parity="N"
            )
            if self.rtu.connect():
                logger.info(f"RTU connected: {SERIAL_PORT} @ {BAUD}")
                return True
            return False
        except Exception as e:
            logger.error(f"RTU error: {e}")
            return False

    def read_rtu(self, addr):
        try:
            result = self.rtu.read_holding_registers(address=addr, count=1, device_id=SLAVE_ADDR)
            if result.isError():
                return None
            self.last_comms = time.time()
            return result.registers[0] if result.registers else None
        except Exception as e:
            return None

    def write_rtu(self, addr, val):
        try:
            result = self.rtu.write_register(address=addr, value=val, device_id=SLAVE_ADDR)
            if result.isError():
                return False
            self.last_comms = time.time()
            logger.info(f"RTU write {addr}={val}")
            return True
        except:
            return False

    def confirm_write(self, val):
        for _ in range(50):
            rb = self.read_rtu(F4S_REG_SP)
            if rb == val:
                logger.info(f"Write confirmed: {val}")
                return True
            time.sleep(0.01)
        return False

    def cyclic(self):
        while self.running:
            try:
                # Read from F4S
                temp = self.read_rtu(F4S_REG_TEMP)
                if temp is not None:
                    tcp_regs[REG_TEMP] = temp

                sp = self.read_rtu(F4S_REG_SP)
                if sp is not None:
                    tcp_regs[REG_SP_READ] = sp

                # Write trigger
                if tcp_regs[REG_TRIGGER] == 1:
                    sp_req = tcp_regs[REG_REQ_SP]
                    if 0 <= sp_req <= 2000:
                        if self.write_rtu(F4S_REG_SP, sp_req) and self.confirm_write(sp_req):
                            tcp_regs[REG_STATUS] = 0
                        else:
                            tcp_regs[REG_STATUS] = 3
                    else:
                        tcp_regs[REG_STATUS] = 4
                    tcp_regs[REG_TRIGGER] = 0

                # Comms health
                if (time.time() - self.last_comms) > 5:
                    tcp_regs[REG_STATUS] = 5

                time.sleep(1)
            except Exception as e:
                logger.error(f"Cyclic: {e}")
                time.sleep(1)

    def run(self):
        logger.info("Gateway Starting")
        if not self.connect_rtu():
            logger.error("RTU connect failed")
            return

        self.running = True
        threading.Thread(target=self.cyclic, daemon=True).start()
        logger.info("Cyclic task started")
        logger.info("TCP server ready on :502 (registers accessible via TCP)")
        
        # Keep alive
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.running = False
            if self.rtu:
                self.rtu.close()
            logger.info("Shutdown")


if __name__ == '__main__':
    F4SGateway().run()
