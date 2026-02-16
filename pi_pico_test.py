import spidev
import time

spi = spidev.SpiDev()
spi.open(0, 0) # Bus 0, Device (Chip Select) 0
spi.max_speed_hz = 1000000 # 1 MHz clock speed

print("Sending 0xAA over SPI. Press Ctrl+C to stop.")

try:
    while True:
        # Send a single byte: 0xAA (10101010 binary)
        spi.xfer2([0xAA])
        # Pause briefly so the scope has time to trigger clearly
        time.sleep(0.01) 
except KeyboardInterrupt:
    spi.close()
    print("Stopped.")