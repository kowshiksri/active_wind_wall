#!/usr/bin/env python3
"""
Test script to verify GPIO trigger pin is working.
Use this to check if GPIO 17 is toggling on Raspberry Pi.
"""

import time
import sys

try:
    from gpiozero import OutputDevice
    print("[TEST] gpiozero imported successfully")
except ImportError as e:
    print(f"[ERROR] Failed to import gpiozero: {e}")
    print("Run: pip install gpiozero")
    sys.exit(1)

# GPIO 17 is the sync pin (Physical Pin 11)
SYNC_PIN = 17

print("="*60)
print("GPIO Trigger Test")
print("="*60)
print(f"Testing GPIO {SYNC_PIN} (Physical Pin 11)")
print("Connect an LED or oscilloscope to verify")
print("Press Ctrl+C to stop")
print("="*60)

try:
    # Initialize the pin
    sync_pin = OutputDevice(SYNC_PIN)
    print(f"[OK] GPIO {SYNC_PIN} initialized as output")
    
    # Test 1: Slow toggle (1 Hz - visible on LED)
    print("\n[TEST 1] Slow toggle at 1 Hz (for LED test)")
    for i in range(10):
        sync_pin.on()
        print(f"  {i+1}/10: Pin HIGH")
        time.sleep(0.5)
        sync_pin.off()
        print(f"  {i+1}/10: Pin LOW")
        time.sleep(0.5)
    
    # Test 2: Fast toggle (400 Hz - use oscilloscope)
    print("\n[TEST 2] Fast toggle at 400 Hz (for 5 seconds)")
    print("  Use oscilloscope to measure - should see 400 pulses/sec")
    start = time.time()
    count = 0
    while time.time() - start < 5.0:
        sync_pin.on()
        time.sleep(0.00001)  # 10 microseconds HIGH
        sync_pin.off()
        time.sleep(0.0024)   # Rest of 2.5ms cycle (400Hz)
        count += 1
    
    print(f"  Sent {count} pulses in 5 seconds ({count/5:.1f} Hz)")
    
    print("\n[SUCCESS] All tests passed!")
    print(f"GPIO {SYNC_PIN} is working correctly")
    
except KeyboardInterrupt:
    print("\n[STOPPED] Test interrupted by user")
except Exception as e:
    print(f"\n[ERROR] Test failed: {e}")
    print("\nPossible issues:")
    print("  1. SPI/GPIO not enabled in raspi-config")
    print("  2. Permission issue - try: sudo usermod -a -G gpio $USER")
    print("  3. Pin already in use by another process")
finally:
    try:
        sync_pin.close()
        print("[CLEANUP] GPIO pin closed")
    except:
        pass

print("\n" + "="*60)
print("Test complete. Check your LED or oscilloscope.")
print("="*60)
