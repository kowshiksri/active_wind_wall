import spidev
import time

spi = spidev.SpiDev()
spi.open(0, 0) # Use SPI bus 0, Chip Select 0 
spi.max_speed_hz = 1000000 # 1 MHz speed 

try:
    while True:
        # Send byte 64 (~25% duty cycle)
        print("Sending low speed...")
        spi.xfer2([64])
        time.sleep(2)
        
        # Send byte 200 (~80% duty cycle)
        print("Sending high speed...")
        spi.xfer2([200])
        time.sleep(2)

except KeyboardInterrupt:
    spi.close()