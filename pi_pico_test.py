import spidev
import time

spi = spidev.SpiDev()
spi.open(0, 0) 
spi.max_speed_hz = 1000000 
spi.mode = 0

PICO_ID = 0x01
SYNC_ID = 0xFF

print("Sending Buffered Data. Motor updates ONLY on Sync.")

try:
    val = 0
    while True:
        # Step 1: Send Data to the specific Pico (Address 0x01)
        # The Pico receives this, but ignores it (stores it in RAM)
        spi.xfer2([PICO_ID, val])
        
        # NOTE: At this exact moment, the motor has NOT moved yet.
        # This simulates filling the buffer of all 4 Picos.
        
        # Step 2: Send the Global Sync Command (Address 0xFF)
        # Now the Pico moves the value from RAM to the Motor
        spi.xfer2([SYNC_ID, 0x00]) # Data byte is ignored during sync
        
        print(f"Loaded: {val} -> SENT SYNC")

        # Ramp logic
        val += 10
        if val > 255: val = 0
            
        # This sleep determines your update frequency (e.g., 0.05s = 20Hz)
        time.sleep(0.05) 

except KeyboardInterrupt:
    spi.close()