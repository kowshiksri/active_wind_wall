#!/usr/bin/env python3
"""Step-by-step hardware diagnostic for the address-framed SPI stream."""

import sys
import time
from typing import Dict, List, Tuple

START_BYTE = 0xA5
END_BYTE = 0x5A
PICO_ID_BITS = 2
MOTOR_ID_BITS = 4
PICO_MASK = (1 << PICO_ID_BITS) - 1
MOTOR_MASK = (1 << MOTOR_ID_BITS) - 1

TOTAL_PICOS = 4
MOTORS_PER_PICO = 9
DEFAULT_PICO_ID = 0
DEFAULT_MOTOR_ID = 0
DEFAULT_IDLE_PWM = 1200
SAFE_MIN_PWM = 1000
SAFE_MAX_PWM = 2000


def encode_address(pico_id: int, motor_id: int) -> int:
    pico_bits = (pico_id & PICO_MASK) << MOTOR_ID_BITS
    motor_bits = motor_id & MOTOR_MASK
    return pico_bits | motor_bits


def clamp_pwm(pwm_us: int) -> int:
    pwm_us = int(pwm_us)
    if pwm_us < SAFE_MIN_PWM:
        return SAFE_MIN_PWM
    if pwm_us > SAFE_MAX_PWM:
        return SAFE_MAX_PWM
    return pwm_us


def build_record(pico_id: int, motor_id: int, pwm_us: int) -> List[int]:
    pwm = clamp_pwm(pwm_us)
    address = encode_address(pico_id, motor_id)
    return [START_BYTE, address, pwm & 0xFF, (pwm >> 8) & 0xFF, END_BYTE]


def build_frame(records: List[Tuple[int, int, int]]) -> List[int]:
    frame: List[int] = []
    for pico_id, motor_id, pwm_us in records:
        frame.extend(build_record(pico_id, motor_id, pwm_us))
    return frame


def build_full_bus_frame(target_map: Dict[Tuple[int, int], int]) -> List[int]:
    records: List[Tuple[int, int, int]] = []
    for pico_id in range(TOTAL_PICOS):
        for motor_id in range(MOTORS_PER_PICO):
            pwm = target_map.get((pico_id, motor_id), DEFAULT_IDLE_PWM)
            records.append((pico_id, motor_id, pwm))
    return build_frame(records)


def describe_frame(frame: List[int], max_records: int = 5) -> None:
    record_count = len(frame) // 5
    print(f"Frame has {len(frame)} bytes ({record_count} records)")
    preview = min(record_count, max_records)
    for idx in range(preview):
        rec = frame[idx * 5 : (idx + 1) * 5]
        addr = rec[1]
        pico_id = (addr >> MOTOR_ID_BITS) & PICO_MASK
        motor_id = addr & MOTOR_MASK
        pwm = rec[2] | (rec[3] << 8)
        print(f"  Record {idx:02d}: Pico {pico_id}, Motor {motor_id} -> {pwm} us")
    if record_count > preview:
        print(f"  ... {record_count - preview} more records suppressed ...")


print("=" * 70)
print("Hardware Diagnostic Test - Addressed SPI Stream")
print("=" * 70)

print("\n[Step 1] Testing imports...")
try:
    import spidev
    print("✓ spidev imported")
except ImportError as exc:  # pragma: no cover
    print(f"✗ spidev import failed: {exc}")
    sys.exit(1)

try:
    import gpiod
    from gpiod.line import Direction, Value
    print("✓ gpiod imported")
except ImportError as exc:  # pragma: no cover
    print(f"✗ gpiod import failed: {exc}")
    sys.exit(1)

print("\n[Step 2] Initializing GPIO pins...")
try:
    gpio_chip = "/dev/gpiochip4"
    sync_pin = 22
    cs_pin = 25  # Manual chip select (physical pin 22)

    config = {
        sync_pin: gpiod.LineSettings(direction=Direction.OUTPUT),
        cs_pin: gpiod.LineSettings(direction=Direction.OUTPUT, output_value=Value.ACTIVE),
    }

    gpio_request = gpiod.request_lines(gpio_chip, consumer="hardware-test", config=config)
    gpio_request.set_value(sync_pin, Value.INACTIVE)
    gpio_request.set_value(cs_pin, Value.ACTIVE)

    print(f"✓ GPIO initialized: Sync={sync_pin}, Manual CS={cs_pin}")
except Exception as exc:  # pragma: no cover
    print(f"✗ GPIO initialization failed: {exc}")
    print("  Hint: Run with sudo")
    sys.exit(1)

print("\n[Step 3] Initializing SPI...")
try:
    spi = spidev.SpiDev()
    spi.open(0, 0)
    spi.max_speed_hz = 1_000_000
    spi.mode = 0
    spi.bits_per_word = 8
    print("✓ SPI initialized: 1 MHz, Mode 0")
except Exception as exc:  # pragma: no cover
    print(f"✗ SPI initialization failed: {exc}")
    sys.exit(1)


def send_frame(frame: List[int]) -> None:
    gpio_request.set_value(cs_pin, Value.INACTIVE)
    spi.writebytes(frame)
    gpio_request.set_value(cs_pin, Value.ACTIVE)


def pulse_sync(duration_s: float = 10e-6) -> None:
    gpio_request.set_value(sync_pin, Value.ACTIVE)
    time.sleep(duration_s)
    gpio_request.set_value(sync_pin, Value.INACTIVE)


print("\n[Step 4] Building single-motor diagnostic frame...")
try:
    pwm_value = 1500
    single_frame = build_frame([(DEFAULT_PICO_ID, DEFAULT_MOTOR_ID, pwm_value)])
    describe_frame(single_frame, max_records=1)
except Exception as exc:  # pragma: no cover
    print(f"✗ Frame build failed: {exc}")
    sys.exit(1)

print("\n[Step 5] Sending diagnostic frame via SPI...")
input("  Press Enter to send frame (monitor Pico PWM output)...")
try:
    send_frame(single_frame)
    print("✓ Frame sent")
except Exception as exc:  # pragma: no cover
    print(f"✗ SPI send failed: {exc}")
    sys.exit(1)

print("\n[Step 6] Sending sync trigger...")
try:
    pulse_sync()
    print("✓ Sync pulse sent")
except Exception as exc:  # pragma: no cover
    print(f"✗ Sync trigger failed: {exc}")
    sys.exit(1)

print("\n[Step 7] Check oscilloscope now!")
print("  Expected on Pico motor pin: ~1.5 ms pulse width")
input("\n  Press Enter to sweep PWM values on the addressed bus...")

print("\n[Step 8] Testing PWM sweep across full bus frame...")
TEST_VALUES = [1100, 1300, 1500, 1700, 1900]

for pwm in TEST_VALUES:
    print(f"\n  Encoding PWM={pwm} us for Pico {DEFAULT_PICO_ID}, Motor {DEFAULT_MOTOR_ID}")
    target_map = {(DEFAULT_PICO_ID, DEFAULT_MOTOR_ID): pwm}
    full_frame = build_full_bus_frame(target_map)
    describe_frame(full_frame)

    try:
        send_frame(full_frame)
        time.sleep(0.001)
        pulse_sync()
        print("  ✓ Frame + sync dispatched. Observe PWM output.")
        time.sleep(2)
    except Exception as exc:  # pragma: no cover
        print(f"  ✗ Failed: {exc}")
        break

print("\n[Step 9] Cleanup...")
try:
    spi.close()
    gpio_request.release()
    print("✓ Resources released")
except Exception:  # pragma: no cover
    pass
