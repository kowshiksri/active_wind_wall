#!/usr/bin/env python3
"""
Step-by-step hardware diagnostic test (FINAL WORKING VERSION).
- Uses GPIO 25 for Manual Chip Select (Connect Pi Pin 22 -> Pico Pin 22/GP17)
- Ignores the Kernel's native CS (GPIO 8) to avoid errors.
"""

import time
import sys

print("="*70)
print("Hardware Diagnostic Test - Step by Step (GPIO 25)")
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
    
    # WE USE GPIO 25 (Physical Pin 22) AS MANUAL CS
    # This avoids conflict with the Kernel's SPI driver on GPIO 8
    cs_pin = 25  
    
    config = {
        sync_pin: gpiod.LineSettings(direction=Direction.OUTPUT),
        cs_pin:   gpiod.LineSettings(direction=Direction.OUTPUT, output_value=Value.ACTIVE) # Start HIGH
    }
    
    gpio_request = gpiod.request_lines(
        gpio_chip,
        consumer="hardware-test",
        config=config
    )
    
    # Set initial states
    gpio_request.set_value(sync_pin, Value.INACTIVE)
    gpio_request.set_value(cs_pin, Value.ACTIVE)
    
    print(f"✓ GPIO initialized: Sync={sync_pin}, Manual CS={cs_pin}")
    
except Exception as e:
    print(f"✗ GPIO initialization failed: {e}")
    print("  Hint: Run with sudo")
    sys.exit(1)

# Step 3: Initialize SPI
print("\n[Step 3] Initializing SPI...")
try:
    spi = spidev.SpiDev()
    spi.open(0, 0)  # SPI0, device 0 (This internally claims GPIO 8, which is fine)
    
    # REMOVED: spi.no_cs = True (This caused Errno 22)
    # We just let the driver toggle GPIO 8 uselessly. We don't use it.
    
    spi.max_speed_hz = 1000000
    spi.mode = 0
    spi.bits_per_word = 8
    print("✓ SPI initialized: 1 MHz, Mode 0")
    
except Exception as e:
    print(f"✗ SPI initialization failed: {e}")
    sys.exit(1)

# Step 4: Test packet building
print("\n[Step 4] Building test packet...")
try:
    pwm_value = 1500
    packet = [0xAA, (pwm_value >> 8) & 0xFF, pwm_value & 0xFF, 0x55]
    print(f"✓ Packet built: {[hex(b) for b in packet]}")
    
except Exception as e:
    print(f"✗ Packet building failed: {e}")
    sys.exit(1)

# Step 5: Send test packet
print("\n[Step 5] Sending packet via SPI...")
input("  Press Enter to send (check oscilloscope on Pico GP14)...")

try:
    # MANUAL CS SEQUENCE
    gpio_request.set_value(cs_pin, Value.INACTIVE) # Pull CS Low (Select)
    spi.writebytes(packet)                         # Send Data
    gpio_request.set_value(cs_pin, Value.ACTIVE)   # Pull CS High (Execute)
    
    print(f"✓ Sent bytes. Manual CS (GPIO {cs_pin}) toggled.")
    
except Exception as e:
    print(f"✗ SPI send failed: {e}")
    sys.exit(1)

# Step 6: Trigger sync pulse
print("\n[Step 6] Sending sync trigger...")
try:
    gpio_request.set_value(sync_pin, Value.ACTIVE)
    time.sleep(0.00001)
    gpio_request.set_value(sync_pin, Value.INACTIVE)
    print("✓ Sync pulse sent")
    
except Exception as e:
    print(f"✗ Sync trigger failed: {e}")
    sys.exit(1)

# Step 7: Check oscilloscope
print("\n[Step 7] Check oscilloscope now!")
print("  Expected on Pico Pin 1 (GP0):")
print("  - Pulse width: ~1.5 ms")
input("\n  Press Enter to test different PWM values...")

# Step 8: Test multiple PWM values
print("\n[Step 8] Testing PWM sweep (min → max)...")
test_values = [1000, 1250, 1500, 1750, 2000]

for pwm in test_values:
    print(f"\n  Sending PWM = {pwm} µs")
    packet = [0xAA, (pwm >> 8) & 0xFF, pwm & 0xFF, 0x55]
    
    try:
        # Manual CS Toggle
        gpio_request.set_value(cs_pin, Value.INACTIVE)
        spi.writebytes(packet)
        gpio_request.set_value(cs_pin, Value.ACTIVE)
        
        # Sync Trigger
        time.sleep(0.001) 
        gpio_request.set_value(sync_pin, Value.ACTIVE)
        time.sleep(0.00001)
        gpio_request.set_value(sync_pin, Value.INACTIVE)
        
        print(f"  Sent. Check oscilloscope.")
        time.sleep(2)
        
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        break

print("\n[Step 9] Cleanup...")
try:
    spi.close()
    gpio_request.release()
    print("✓ Resources released")
except:
    pass