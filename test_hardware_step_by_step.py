#!/usr/bin/env python3
import spidev
import time
import sys

print("\n" + "="*60)
print("STEP 3: ADDRESSED PACKET TEST")
print("="*60)

# Packet format: [START, ADDRESS, INTENSITY, END]
PACKET_START = 0xAA
PACKET_END = 0x55

def build_packet(address, intensity):
    """Build a 4-byte packet: [START, ADDRESS, INTENSITY, END]"""
    if intensity > 100:
        intensity = 100
    return [PACKET_START, address, intensity, PACKET_END]

print("\n[Step 1] Checking hardware...")
try:
    import os
    if os.path.exists("/dev/spidev0.0"):
        print("✓ SPI device found: /dev/spidev0.0")
    else:
        print("✗ SPI device not found!")
        sys.exit(1)
except Exception as exc:
    print(f"✗ Check failed: {exc}")
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
except Exception as exc:
    print(f"✗ SPI initialization failed: {exc}")
    sys.exit(1)

print("\n[Step 4] Testing addressed packets...")
print("  Sending 4 packets in ONE SPI transaction (CS stays LOW)")
print("  Each packet: [0xAA, ADDRESS, INTENSITY, 0x55]")
print()

# Test: Send 4 motor packets (addresses 0-3) in one transaction
test_packets = [
    (0, 25),   # Motor 0: 25%
    (1, 50),   # Motor 1: 50%
    (2, 75),   # Motor 2: 75%
    (3, 100),  # Motor 3: 100%
]

# Build complete data stream
data_stream = []
for addr, intensity in test_packets:
    packet = build_packet(addr, intensity)
    data_stream.extend(packet)
    print(f"  Motor {addr}: {intensity:3d}% → Packet: {[hex(b) for b in packet]}")

print(f"\nTotal bytes to send: {len(data_stream)} (4 packets × 4 bytes)")
print("Sending in ONE SPI transaction...")

try:
    response = spi.xfer2(data_stream)
    print(f"\n✓ Sent {len(data_stream)} bytes")
    print(f"  Response: {[hex(b) for b in response[:16]]}")
except Exception as exc:
    print(f"✗ SPI write failed: {exc}")
    sys.exit(1)

print("\n[Step 5] Watch the Pico...")
print("  LED should: heartbeat (blink slowly)")
print("           + quick flash for each valid packet")
print("  PWM should: change on GPIO14 as addressed motors update")

for countdown in range(5, 0, -1):
    print(f"Continuing in {countdown}s...", end='\r')
    time.sleep(1)

print("\n[Step 6] Sweep test with addressing...")
print("  Sending 20 sequential packets to motors 0-3")
print()

data_stream = []
for i in range(5):
    intensity = int((i / 4) * 100)  # 0% -> 100% in 5 steps
    for motor in range(4):
        packet = build_packet(motor, intensity)
        data_stream.extend(packet)
    print(f"  Step {i+1}: Intensity {intensity:3d}%")

print(f"\nSending {len(data_stream)} bytes total...")
try:
    response = spi.xfer2(data_stream)
    print(f"✓ Sent successfully")
except Exception as exc:
    print(f"✗ Failed: {exc}")

print("\nTest complete!")
spi.close()
print("✓ SPI connection closed")
