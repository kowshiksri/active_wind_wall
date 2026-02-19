#!/usr/bin/env python3
import time
import spidev
import gpiod
from gpiod.line import Direction, Value

# ---------------------------
# CONFIGURATION
# ---------------------------
SPI_BUS = 0
SPI_DEV = 0           # /dev/spidev0.0
SPI_SPEED_HZ = 500_000
SYNC_PIN = 22         # BCM22 on Pi header (physical pin 15)

PICO_ID = 0
MOTORS_PER_PICO = 9

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
# SETUP SYNC GPIO (output)
# ---------------------------
chip_name = "/dev/gpiochip4"   # Pi 5 GPIO chip
config = {
    SYNC_PIN: gpiod.LineSettings(direction=Direction.OUTPUT)
}
request = gpiod.request_lines(chip_name, consumer="pico-spi-test", config=config)
request.set_value(SYNC_PIN, Value.INACTIVE)
print(f"[GPIO] SYNC pin configured on GPIO {SYNC_PIN}")

def pulse_sync():
    # 10us pulse
    request.set_value(SYNC_PIN, Value.ACTIVE)
    time.sleep(0.00001)
    request.set_value(SYNC_PIN, Value.INACTIVE)

# ---------------------------
# TEST LOOP
# ---------------------------
try:
    frame_counter = 0
    while True:
        # 1) Build a 36-byte test frame
        base = list(range(36))  # 0..35
        test_frame = [(b ^ (frame_counter & 0xFF)) & 0xFF for b in base]

        start = PICO_ID * MOTORS_PER_PICO
        end = start + MOTORS_PER_PICO
        expected_slice = test_frame[start:end]

        # 2) Tell Pico to start a new frame
        pulse_sync()
        # Small delay so Pico main loop sees start_new_frame
        time.sleep(0.0001)

        # 3) Send 36-byte frame; Pico is blocking and reading these
        spi.xfer2(test_frame)

        # 4) Give Pico time to copy + preload TX FIFO
        time.sleep(0.001)  # 1ms is plenty

        # 5) Read back 9 bytes from Pico (Pico has preloaded them)
        read_back = spi.xfer2([0x00] * MOTORS_PER_PICO)

        print(f"Frame {frame_counter}:")
        print(f"  Sent slice    ({start}:{end}): {expected_slice}")
        print(f"  Read back from Pico       : {read_back}")
        print()

        frame_counter += 1
        time.sleep(0.1)

except KeyboardInterrupt:
    print("Exiting...")

finally:
    spi.close()
    print("[SPI] Closed")
