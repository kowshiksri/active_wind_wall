#!/usr/bin/env python3
"""
Step-by-step hardware diagnostic test (FIXED FOR MANUAL CS).
Tests each component of the SPI/GPIO pipeline independently.
Run with: sudo python3 test_hardware_step_by_step.py
"""

import time
import sys

print("="*70)
print("Hardware Diagnostic Test - Step by Step (Manual CS Fix)")
print("="*70)

# Step 1: Test imports
print("\n[Step 1] Testing imports...")
try:
    import spidev
    print("✓ spidev imported")
except ImportError as e:
    print(f"✗ spidev import failed: {e}")
    sys.exit(1)

try:
    import gpiod
    from gpiod.line import Direction, Value
    print("✓ gpiod imported")
except ImportError as e:
    print(f"✗ gpiod import failed: {e}")
    sys.exit(1)

# Step 2: Initialize GPIO
print("\n[Step 2] Initializing GPIO pins...")
try:
    gpio_chip = '/dev/gpiochip4'
    sync_pin = 22
    cs_pin = 8  # <--- WE ARE CLAIMING THIS NOW

    config = {
        sync_pin: gpiod.LineSettings(direction=Direction.OUTPUT),
        cs_pin:   gpiod.LineSettings(direction=Direction.OUTPUT, output_value=Value.ACTIVE) # Start HIGH (Deselected)
    }
    
    gpio_request = gpiod.request_lines(
        gpio_chip,
        consumer="hardware-test",
        config=config
    )
    
    # Set initial states explicitly just to be sure
    gpio_request.set_value(sync_pin, Value.INACTIVE)  # Sync LOW
    gpio_request.set_value(cs_pin, Value.ACTIVE)      # CS HIGH (deselected)
    
    print(f"✓ GPIO initialized: Sync={sync_pin}, CS={cs_pin}")
    
except Exception as e:
    print(f"✗ GPIO initialization failed: {e}")
    print("  Hint: Run with sudo, or add user to gpio group")
    sys.exit(1)

# Step 3: Initialize SPI
print("\n[Step 3] Initializing SPI...")
try:
    spi = spidev.SpiDev()
    spi.open(0, 0)  # SPI0, device 0
    spi.no_cs = True  # <--- CRITICAL: Disable automatic CS so we can control it manually
    spi.max_speed_hz = 1000000  # 1 MHz
    spi.mode = 0  # Mode 0
    spi.bits_per_word = 8
    print("✓ SPI initialized: 1 MHz, Mode 0, Manual CS")
    
except Exception as e:
    print(f"✗ SPI initialization failed: {e}")
    print("  Hint: Enable SPI with raspi-config")
    sys.exit(1)

# Step 4: Test packet building
print("\n[Step 4] Building test packet...")
try:
    # Single motor, PWM = 1500 µs (middle value)
    pwm_value = 1500
    
    # Packet format: [0xAA, PWM_HIGH, PWM_LOW, 0x55]
    packet = [
        0xAA,  # Start byte
        (pwm_value >> 8) & 0xFF,  # High byte
        pwm_value & 0xFF,         # Low byte
        0x55   # End byte
    ]
    
    print(f"✓ Packet built: {[hex(b) for b in packet]}")
    print(f"  PWM value: {pwm_value} µs")
    
except Exception as e:
    print(f"✗ Packet building failed: {e}")
    sys.exit(1)

# Step 5: Send test packet
print("\n[Step 5] Sending packet via SPI...")
input("  Press Enter to send (check oscilloscope is connected to GPIO 14)...")

try:
    # --- MANUAL CHIP SELECT SEQUENCE ---
    # 1. Pull CS Low (Wake up Pico)
    gpio_request.set_value(cs_pin, Value.INACTIVE)
    
    # 2. Send Data
    spi.writebytes(packet)
    
    # 3. Pull CS High (Sleep/Execute)
    gpio_request.set_value(cs_pin, Value.ACTIVE)
    # -----------------------------------
    
    print(f"✓ Sent {len(packet)} bytes via SPI (Manually toggled CS)")
    
except Exception as e:
    print(f"✗ SPI send failed: {e}")
    sys.exit(1)

# Step 6: Trigger sync pulse
print("\n[Step 6] Sending sync trigger...")
try:
    gpio_request.set_value(sync_pin, Value.ACTIVE)   # HIGH
    time.sleep(0.00001)  # 10 µs pulse
    gpio_request.set_value(sync_pin, Value.INACTIVE)  # LOW
    print("✓ Sync pulse sent (10 µs)")
    
except Exception as e:
    print(f"✗ Sync trigger failed: {e}")
    sys.exit(1)

# Step 7: Check oscilloscope
print("\n[Step 7] Check oscilloscope now!")
print("  Expected on GPIO 14:")
print("  - Pulse width: ~1.5 ms (1500 µs)")
print("  - Period: ~16 ms (62.5 Hz)")
print("  - Voltage: 0-3.3V square wave")
input("\n  Press Enter to test different PWM values...")

# Step 8: Test multiple PWM values
print("\n[Step 8] Testing PWM sweep (min → max)...")
test_values = [1000, 1250, 1500, 1750, 2000]

for pwm in test_values:
    print(f"\n  Sending PWM = {pwm} µs")
    
    # Build packet
    packet = [0xAA, (pwm >> 8) & 0xFF, pwm & 0xFF, 0x55]
    
    # Send via SPI with Manual CS
    try:
        # 1. Select (Low)
        gpio_request.set_value(cs_pin, Value.INACTIVE)
        
        # 2. Write
        spi.writebytes(packet)
        
        # 3. Deselect (High)
        gpio_request.set_value(cs_pin, Value.ACTIVE)
        
        # Small delay to let SPI finish before triggering sync
        time.sleep(0.001) 
        
        # Trigger sync pulse
        gpio_request.set_value(sync_pin, Value.ACTIVE)
        time.sleep(0.00001)  # 10 µs pulse
        gpio_request.set_value(sync_pin, Value.INACTIVE)
        
        print(f"  Sent. Check oscilloscope (pulse should be ~{pwm/1000:.1f} ms)")
        time.sleep(2)  # Wait 2s between updates
        
    except Exception as e:
        print(f"  ✗ Failed to send PWM {pwm}: {e}")
        break

print("\n[Step 9] Cleanup...")
try:
    spi.close()
    gpio_request.release()
    print("✓ Resources released")
except:
    pass

print("\n" + "="*70)
print("Diagnostic complete!")
print("="*70)
print("\nDid you see PWM changes on the oscilloscope?")
print("  YES → Hardware working! Issue is in flight loop code")
print("  NO  → Check wiring or Pico firmware")
print("="*70)