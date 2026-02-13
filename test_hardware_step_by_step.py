#!/usr/bin/env python3
"""
STEP 2: Simple SPI PWM Control Test
====================================

WIRING (Raspberry Pi 5 → Pico 2):
----------------------------------
Pi Pin 19 (GPIO10 MOSI) → Pico Pin 25 (GP19)
Pi Pin 23 (GPIO11 SCLK) → Pico Pin 24 (GP18)
Pi Pin 22 (GPIO25 CS*)  → Pico Pin 22 (GP17)  *Manual CS
Pi Pin 25 (GND)         → Pico Pin 18 (GND)

OSCILLOSCOPE:
-------------
Probe: Pico Pin 19 (GP14) - PWM output

WHAT THIS DOES:
---------------
Sends simple 4-byte packets: [0xAA, PWM_HIGH, PWM_LOW, 0x55]
Tests PWM control from 1200 µs to 1900 µs
LED on Pico blinks when packets are received
"""

import sys
import time

# Simple packet format for Step 2
START_BYTE = 0xAA
END_BYTE = 0x55
SAFE_MIN_PWM = 1000
SAFE_MAX_PWM = 2700


def clamp_pwm(pwm_us: int) -> int:
    """Clamp PWM to safe range."""
    pwm_us = int(pwm_us)
    if pwm_us < SAFE_MIN_PWM:
        return SAFE_MIN_PWM
    if pwm_us > SAFE_MAX_PWM:
        return SAFE_MAX_PWM
    return pwm_us


def build_packet(pwm_us: int) -> list:
    """Build 4-byte packet: [START, PWM_HIGH, PWM_LOW, END]."""
    pwm = clamp_pwm(pwm_us)
    return [START_BYTE, (pwm >> 8) & 0xFF, pwm & 0xFF, END_BYTE]


print("=" * 70)
print("STEP 2: Simple SPI PWM Control Test")
print("=" * 70)
print("\nWIRING CHECK:")
print("  Pi GPIO10 (MOSI, Pin 19) → Pico GP19 (Pin 25)")
print("  Pi GPIO11 (SCLK, Pin 23) → Pico GP18 (Pin 24)")
print("  Pi GPIO25 (CS,   Pin 22) → Pico GP17 (Pin 22)")
print("  Pi GND    (Pin 25)       → Pico GND  (Pin 18)")
print("\nOscilloscope: Probe Pico GP14 (Pin 19) for PWM output")
print("=" * 70)

print("\n[Step 1] Testing imports...")
try:
    import spidev
    print("✓ spidev imported")
except ImportError as exc:
    print(f"✗ spidev import failed: {exc}")
    sys.exit(1)

try:
    import gpiod
    from gpiod.line import Direction, Value
    print("✓ gpiod imported")
except ImportError as exc:
    print(f"✗ gpiod import failed: {exc}")
    sys.exit(1)

print("\n[Step 2] SPI will use hardware CS on GPIO8 (Pin 24)...")
print("  Make sure Pico GP17 is connected to Pi Pin 24 (GPIO8)")
input("  Press Enter when wiring is correct...")

print("\n[Step 3] Initializing SPI...")
try:
    spi = spidev.SpiDev()
    spi.open(0, 0)
    spi.max_speed_hz = 1_000_000
    spi.mode = 0
    spi.bits_per_word = 8
    print("✓ SPI initialized: 1 MHz, Mode 0")
    print(f"  Hardware CS (GPIO8) will toggle automatically")
except Exception as exc:
    print(f"✗ SPI initialization failed: {exc}")
    sys.exit(1)


def send_packet(packet: list) -> None:
    """Send packet - hardware CS toggles automatically."""
    spi.writebytes(packet)


print("\n[Step 4] Testing PWM control...")
test_values = [1200, 1400, 1500, 1700, 1900]

for pwm in test_values:
    packet = build_packet(pwm)
    print(f"\nSending PWM = {pwm} µs")
    print(f"  Packet: {[hex(b) for b in packet]}")
    
    try:
        send_packet(packet)
        print(f"  ✓ Sent. Check oscilloscope for {pwm} µs pulse.")
        time.sleep(2)  # Wait 2 seconds between tests
    except Exception as exc:
        print(f"  ✗ Failed: {exc}")
        break

print("\n[Step 5] Cleanup...")
try:
    spi.close()
    gpio_request.release()
    print("✓ Resources released")
except Exception:
    pass

print("\n" + "=" * 70)
print("Test complete! Check oscilloscope for PWM changes.")
print("=" * 70)
