#!/usr/bin/env python3
import time
import spidev
import gpiod
from gpiod.line import Direction, Value

# ---------------------------
# CONFIG
# ---------------------------
SPI_BUS = 0
SPI_DEV = 0           # /dev/spidev0.0
SPI_SPEED_HZ = 500_000
SYNC_PIN = 22         # BCM22 (physical pin 15) on Pi

TOTAL_MOTORS = 36

# ---------------------------
# SETUP SPI
# ---------------------------
spi = spidev.SpiDev()
spi.open(SPI_BUS, SPI_DEV)
spi.max_speed_hz = SPI_SPEED_HZ
spi.mode = 0
spi.bits_per_word = 8

print(f"[SPI] Opened /dev/spidev{SPI_BUS}.{SPI_DEV} at {SPI_SPEED_HZ} Hz")

# ---------------------------
# SETUP SYNC GPIO
# ---------------------------
chip_name = "/dev/gpiochip4"   # Pi 5
config = {
    SYNC_PIN: gpiod.LineSettings(direction=Direction.OUTPUT)
}
request = gpiod.request_lines(chip_name, consumer="pico-byte-counter-test", config=config)
request.set_value(SYNC_PIN, Value.INACTIVE)
print(f"[GPIO] SYNC pin configured on GPIO {SYNC_PIN}")

def pulse_sync():
    request.set_value(SYNC_PIN, Value.ACTIVE)
    time.sleep(0.00001)  # 10 us
    request.set_value(SYNC_PIN, Value.INACTIVE)

# ---------------------------
# TEST LOOP
# ---------------------------
try:
    frame_counter = 0
    while True:
        # 1) Build one 36-byte frame: 0..35 XOR frame_counter
        base = list(range(TOTAL_MOTORS))
        frame = [(b ^ (frame_counter & 0xFF)) & 0xFF for b in base]

        # 2) Send each byte separately so CS toggles per byte
        for b in frame:
            spi.xfer2([b])

        # 3) Pulse SYNC to latch frame on all Picos
        pulse_sync()

        print(f"Sent frame {frame_counter} (0..35 XOR {frame_counter & 0xFF})")
        frame_counter += 1
        time.sleep(0.1)   # 10 Hz update; adjust as you like

except KeyboardInterrupt:
    print("Exiting...")

finally:
    spi.close()
    print("[SPI] Closed")
