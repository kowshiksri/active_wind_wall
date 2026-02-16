import spidev
import RPi.GPIO as GPIO
import time

# SPI Setup
spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 1000000 

# TRIGGER Pin Setup
TRIGGER_PIN = 25
GPIO.setmode(GPIO.BCM)
GPIO.setup(TRIGGER_PIN, GPIO.OUT)
GPIO.output(TRIGGER_PIN, 0) # Start Low

print("Sending Data... Motor only moves when Trigger pulses.")

try:
    val = 0
    while True:
        # 1. LOAD: Send the data over SPI
        # The Pico receives this and updates 'next_pwm_val', but motor doesn't move.
        spi.xfer2([val])
        
        # Small delay to ensure SPI transmission is totally done
        # (In reality this can be microseconds)
        time.sleep(0.001) 

        # 2. FIRE: Pulse the Trigger Line
        # This tells ALL connected Picos to update simultaneously
        GPIO.output(TRIGGER_PIN, 1)
        # Short pulse is enough (pico is fast)
        time.sleep(0.0001) 
        GPIO.output(TRIGGER_PIN, 0)

        print(f"Loaded {val} -> FIRED Trigger")
        
        val += 5
        if val > 255: val = 0
        time.sleep(0.05) # 20Hz update rate

except KeyboardInterrupt:
    spi.close()
    GPIO.cleanup()