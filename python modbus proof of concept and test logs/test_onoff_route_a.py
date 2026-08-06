#!/usr/bin/env python3
"""Offline test of the Route A on/off path in f4s_gateway.

No serial port and no F4 required: the RTU accessors are replaced with a
simulated controller holding just the registers the on/off route touches.
That is enough to prove the decision logic, because everything Route A does
to the F4 is an ordinary holding-register read or write.

Run:  python3 python modbus proof of concept and test logs/test_onoff_route_a.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import f4s_gateway as gw


class FakeF4:
    """The subset of the F4 register map that Route A reads or writes."""

    def __init__(self, sp_low_limit_x10=-400, sp_x10=280, profile=0):
        self.regs = {
            gw.F4S_REG_SP: gw.i16_to_u16(sp_x10),
            gw.F4S_REG_SP_LOW_LIMIT: gw.i16_to_u16(sp_low_limit_x10),
            gw.F4S_REG_PROFILE_NOW: profile,
            gw.F4S_REG_TEMP: gw.i16_to_u16(275),
        }
        self.writes = []

    def read(self, addr):
        return self.regs.get(addr)

    def write(self, addr, value):
        self.writes.append((addr, value))
        if addr == gw.F4S_REG_TERMINATE:
            # Terminating a profile leaves all outputs off and clears the
            # running-profile status, exactly as the manual describes.
            self.regs[gw.F4S_REG_PROFILE_NOW] = 0
        else:
            self.regs[addr] = value
        return True


def make_gateway(fake):
    g = gw.F4SGateway()
    g.read_rtu_reg = fake.read
    g.write_rtu_reg = fake.write
    return g


def tcp_set(reg, value):
    with gw.hr_lock:
        gw.device.setValues(gw.FC_HOLDING, reg, [value])


def tcp_get(reg):
    with gw.hr_lock:
        return gw.device.getValues(gw.FC_HOLDING, reg, 1)[0]


def reset_tcp():
    for reg in range(10):
        tcp_set(reg, 0)


results = []


def check(name, condition, detail=""):
    results.append((name, condition, detail))
    print(f"{'PASS' if condition else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


# --- 1. OFF sentinel is derived from the controller, not hard-coded ---------
reset_tcp()
fake = FakeF4(sp_low_limit_x10=-400, sp_x10=280)
g = make_gateway(fake)
g.ensure_off_sentinel()
check(
    "OFF sentinel = low limit - 1",
    g.off_sentinel == -401,
    f"got {g.off_sentinel}",
)
check(
    "low limit published to CODESYS (reg 7)",
    gw.u16_to_i16(tcp_get(gw.REG_SP_LOW)) == -400,
)

# --- 2. No command at start-up leaves the cabinet alone ---------------------
reset_tcp()
fake = FakeF4(sp_x10=280)
g = make_gateway(fake)
g.service_onoff(fake.read(gw.F4S_REG_SP), gw.i16_to_u16(280))
check(
    "CMD_NONE writes nothing",
    fake.writes == [],
    f"writes={fake.writes}",
)
check("state echoes ON", tcp_get(gw.REG_ONOFF_STATE) == gw.STATE_ON)

# --- 3. OFF writes the sentinel --------------------------------------------
tcp_set(gw.REG_ONOFF_CMD, gw.CMD_OFF)
g.service_onoff(fake.read(gw.F4S_REG_SP), gw.i16_to_u16(280))
check(
    "CMD_OFF writes sentinel to reg 300",
    (gw.F4S_REG_SP, gw.i16_to_u16(-401)) in fake.writes,
    f"writes={fake.writes}",
)
check("state echoes OFF", tcp_get(gw.REG_ONOFF_STATE) == gw.STATE_OFF)

# --- 4. A held OFF command does not keep writing ---------------------------
fake.writes.clear()
for _ in range(3):
    g.service_onoff(fake.read(gw.F4S_REG_SP), gw.i16_to_u16(280))
check(
    "steady OFF is idle on the RTU link",
    fake.writes == [],
    f"writes={fake.writes}",
)

# --- 5. ON restores the staged setpoint ------------------------------------
tcp_set(gw.REG_ONOFF_CMD, gw.CMD_ON)
g.service_onoff(fake.read(gw.F4S_REG_SP), gw.i16_to_u16(280))
check(
    "CMD_ON restores staged setpoint",
    fake.regs[gw.F4S_REG_SP] == gw.i16_to_u16(280),
    f"reg300={gw.u16_to_i16(fake.regs[gw.F4S_REG_SP])}",
)
check("state echoes ON again", tcp_get(gw.REG_ONOFF_STATE) == gw.STATE_ON)

# --- 6. ON with an out-of-range staged setpoint is refused -----------------
reset_tcp()
fake = FakeF4(sp_x10=-401)
g = make_gateway(fake)
g.service_onoff(fake.read(gw.F4S_REG_SP), 0)     # learn sentinel, observe OFF
tcp_set(gw.REG_ONOFF_CMD, gw.CMD_ON)
fake.writes.clear()
g.service_onoff(fake.read(gw.F4S_REG_SP), gw.i16_to_u16(9999))
check(
    "ON refused when staged setpoint is out of range",
    fake.writes == [] and tcp_get(gw.REG_STATUS) == gw.ST_RANGE,
    f"writes={fake.writes} status={tcp_get(gw.REG_STATUS)}",
)

# --- 7. A running profile is terminated before the sentinel is written -----
reset_tcp()
fake = FakeF4(sp_x10=280, profile=3)
g = make_gateway(fake)
g.service_onoff(fake.read(gw.F4S_REG_SP), gw.i16_to_u16(280))
tcp_set(gw.REG_ONOFF_CMD, gw.CMD_OFF)
g.service_onoff(fake.read(gw.F4S_REG_SP), gw.i16_to_u16(280))
addrs = [a for a, _ in fake.writes]
check(
    "profile terminated before sentinel write",
    gw.F4S_REG_TERMINATE in addrs
    and addrs.index(gw.F4S_REG_TERMINATE) < addrs.index(gw.F4S_REG_SP),
    f"write order={addrs}",
)
check("running profile published (reg 8)", tcp_get(gw.REG_PROFILE) == 3)

# --- 8. State follows the controller, not the last command -----------------
# Someone turns the setpoint off at the F4 keypad while CODESYS commands ON.
# The echo must report OFF, and the gateway must act to restore ON.
reset_tcp()
fake = FakeF4(sp_x10=280)
g = make_gateway(fake)
tcp_set(gw.REG_REQ_SP, gw.i16_to_u16(280))
g.service_onoff(fake.read(gw.F4S_REG_SP), gw.i16_to_u16(280))
tcp_set(gw.REG_ONOFF_CMD, gw.CMD_ON)
fake.regs[gw.F4S_REG_SP] = gw.i16_to_u16(-401)    # keypad turned it off
g.service_onoff(fake.read(gw.F4S_REG_SP), gw.i16_to_u16(280))
check(
    "keypad OFF is observed and corrected under CMD_ON",
    fake.regs[gw.F4S_REG_SP] == gw.i16_to_u16(280),
    f"reg300={gw.u16_to_i16(fake.regs[gw.F4S_REG_SP])}",
)

failed = [n for n, ok, _ in results if not ok]
print()
print(f"{len(results) - len(failed)}/{len(results)} passed")
if failed:
    print("FAILED: " + ", ".join(failed))
sys.exit(1 if failed else 0)
