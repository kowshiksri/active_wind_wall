# spi_scope_test.py
# Run on Raspberry Pi 5 only.
# Purpose: Verify SPI packet integrity and SYNC timing on oscilloscope.
# No changes to Pico firmware needed.
#
# Scope setup:
#   CH1: MOSI (GPIO 10)
#   CH2: SCLK (GPIO 11)
#   CH3: SYNC (GPIO 22)  <- trigger source, rising edge
#   CH4: Optional - a spare GPIO used as "SPI_ACTIVE" marker (GPIO 24)
#
# What to look for:
#   - CH3 (SYNC) must rise AFTER the last SCK edge on CH2, not during or before.
#   - Count bytes on CH1/CH2: should be exactly 38 bytes (start + 36 data + end)
#     or 36 bytes if you switch to fixed-length. Currently 38.
#   - CH1 first byte should read 10101010 = 0xAA (start byte as per current firmware)

import spidev
import gpiod
from gpiod.line import Direction, Value
import time

# ---- Config ----
SPI_BUS        = 0
SPI_DEVICE     = 0
SPI_SPEED_HZ   = 1_000_000   # 1MHz, same as firmware
SPI_MODE       = 0            # Test with mode 0 first (Pico default slave mode)

SYNC_PIN       = 22
MARKER_PIN     = 24           # Optional scope marker: HIGH during writebytes(), LOW after
GPIO_CHIP      = '/dev/gpiochip4'  # Pi 5

PACKET_START   = 0xAA
PACKET_END     = 0x55
TOTAL_MOTORS   = 36

# ---- Test Modes ----
# Change TEST_MODE to switch what value all 36 motors are commanded to.
# This makes the MOSI pattern easy to verify on scope.
#
#   'idle'    -> all motors 0x00  (Pico applies 1000us)
#   'mid'     -> all motors 0x80  (Pico applies ~1600us)
#   'max'     -> all motors 0xFF  (Pico applies 2000us)
#   'pattern' -> alternating 0x00 / 0xFF (checkerboard, easy to see on scope)
#   'ramp'    -> motors 0..35 get byte values 0,7,14,21...255 (linear ramp)

TEST_MODE = 'mid'

# ---- Build packet ----
def build_packet(test_mode: str) -> list:
    if test_mode == 'idle':
        data = [0x00] * TOTAL_MOTORS
    elif test_mode == 'mid':
        data = [0x80] * TOTAL_MOTORS        # 0x80 = 128 -> ~1596us on Pico
    elif test_mode == 'max':
        data = [0xFF] * TOTAL_MOTORS
    elif test_mode == 'pattern':
        data = [0xFF if i % 2 == 0 else 0x00 for i in range(TOTAL_MOTORS)]
    elif test_mode == 'ramp':
        data = [min(255, int(i * 255 / (TOTAL_MOTORS - 1))) for i in range(TOTAL_MOTORS)]
    else:
        raise ValueError(f"Unknown test mode: {test_mode}")

    packet = [PACKET_START] + data + [PACKET_END]
    assert len(packet) == TOTAL_MOTORS + 2, f"Packet length wrong: {len(packet)}"
    return packet

# ---- Expected byte math ----
def byte_to_pwm(b: int) -> float:
    """What PWM us should the Pico produce for this byte value (per current firmware)."""
    if b == 0x00:
        return 1000.0
    return 1200.0 + (b * 800.0 / 255.0)

# ---- Init hardware ----
spi = spidev.SpiDev()
spi.open(SPI_BUS, SPI_DEVICE)
spi.max_speed_hz = SPI_SPEED_HZ
spi.mode = SPI_MODE
spi.bits_per_word = 8
print(f"[SPI] Opened SPI{SPI_BUS}.{SPI_DEVICE} at {SPI_SPEED_HZ}Hz mode {SPI_MODE}")

gpio_config = {
    SYNC_PIN:   gpiod.LineSettings(direction=Direction.OUTPUT),
    MARKER_PIN: gpiod.LineSettings(direction=Direction.OUTPUT),
}
lines = gpiod.request_lines(GPIO_CHIP, consumer="spi-scope-test", config=gpio_config)
lines.set_value(SYNC_PIN,   Value.INACTIVE)
lines.set_value(MARKER_PIN, Value.INACTIVE)
print(f"[GPIO] SYNC={SYNC_PIN}, MARKER={MARKER_PIN} initialized LOW")

# ---- Print what to expect on scope ----
packet = build_packet(TEST_MODE)
print(f"\n[TEST] Mode: {TEST_MODE}")
print(f"[TEST] Packet length: {len(packet)} bytes")
print(f"[TEST] Packet bytes: {[hex(b) for b in packet]}")
print(f"[TEST] Expected byte 0 (START): {hex(packet[0])} -> should be 0xAA")
print(f"[TEST] Expected byte 1 (motor 0): {hex(packet[1])} -> ~{byte_to_pwm(packet[1]):.0f}us on Pico motor 0")
print(f"[TEST] Expected last byte (END): {hex(packet[-1])} -> should be 0x55")
print(f"\n[TEST] At 1MHz SPI, {len(packet)} bytes takes {len(packet)*8:.0f}us to clock out")
print(f"[TEST] SYNC pulse fires 100us AFTER writebytes() returns")
print(f"[TEST] Scope: trigger on SYNC (CH3) rising edge, check CH2 last SCK edge is BEFORE it")
print(f"\nStarting in 3 seconds... Ctrl+C to stop\n")
time.sleep(3)

# ---- Main test loop ----
# Sends at 1Hz so scope can capture comfortably.
# After you confirm timing, change SEND_RATE_HZ to 400 to test at real rate.

SEND_RATE_HZ = 1        # Change to 400 after scope confirms 1Hz looks correct
SEND_INTERVAL = 1.0 / SEND_RATE_HZ
frame_count = 0

try:
    while True:
        t_start = time.monotonic()

        # Mark start of SPI transaction on scope (CH4 goes HIGH)
        lines.set_value(MARKER_PIN, Value.ACTIVE)

        # Send packet
        spi.writebytes(packet)

        # Mark end of SPI transaction (CH4 goes LOW)
        # The gap between CH4 falling and CH3 (SYNC) rising is the margin.
        # This should be > 0. If it is negative, SYNC fires before bytes are out.
        lines.set_value(MARKER_PIN, Value.INACTIVE)

        # Deliberate delay before SYNC.
        # At 1MHz, 38 bytes = 304us. writebytes() on Linux should block until done,
        # but kernel SPI driver buffers can cause uncertainty. This 100us guard ensures
        # the last bit is definitely clocked before SYNC fires.
        # If scope shows SYNC already after last SCK with 0us delay, remove this.
        time.sleep(0.0001)   # 100us guard delay — adjust based on scope observation

        # Fire SYNC pulse
        lines.set_value(SYNC_PIN, Value.ACTIVE)
        time.sleep(0.00001)  # 10us pulse width
        lines.set_value(SYNC_PIN, Value.INACTIVE)

        frame_count += 1
        if frame_count % 10 == 0:
            print(f"[TEST] Frame {frame_count} sent (mode={TEST_MODE}, rate={SEND_RATE_HZ}Hz)")

        # Wait for next frame slot
        elapsed = time.monotonic() - t_start
        remaining = SEND_INTERVAL - elapsed
        if remaining > 0:
            time.sleep(remaining)
        else:
            # We overran — this matters at 400Hz
            print(f"[WARN] Frame overrun by {-remaining*1e6:.0f}us at frame {frame_count}")

except KeyboardInterrupt:
    print("\n[TEST] Stopped.")

finally:
    lines.set_value(SYNC_PIN,   Value.INACTIVE)
    lines.set_value(MARKER_PIN, Value.INACTIVE)
    spi.close()
    lines.release()
    print("[TEST] Hardware released.")