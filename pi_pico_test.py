import spidev
import time

# SPI Setup
spi = spidev.SpiDev()
spi.open(0, 0) # Bus 0, Device 0 (CE0)
spi.max_speed_hz = 1000000 
spi.mode = 0

print("Sending Sweeping Data (0-255). Press Ctrl+C to stop.")

try:
    val = 0
    direction = 1
    
    while True:
        # Send the current value as a single byte
        spi.xfer2([val])
        
        # Print for debug visibility
        # 0 = 1000us, 127 = ~1500us, 255 = 2000us
        print(f"Sent: {val} (Approx PWM: {1000 + (val*1000)//255} us)")

        # Increment value to create a sweep effect
        val += 5
        if val > 255:
            val = 0
            
        # Update rate: 20Hz (Sleep 0.05s)
        # If you stop this script, the Pico watchdog should trigger after 0.1s
        time.sleep(0.05) 

except KeyboardInterrupt:
    spi.close()
    print("\nStopped. Pico should revert to 1500us (Default).")