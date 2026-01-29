import time
import gpiod
from gpiod.line import Direction, Value

GPIO_LINE = 18        # BCM GPIO18 (physical pin 12)
FREQ = 1000           # 1 kHz
DUTY = 0.5
DURATION = 10

period = 1.0 / FREQ
t_on = period * DUTY
t_off = period * (1 - DUTY)

with gpiod.request_lines(
    "/dev/gpiochip0",
    consumer="pwm-test",
    config={
        GPIO_LINE: gpiod.LineSettings(
            direction=Direction.OUTPUT,
            output_value=Value.INACTIVE,
        )
    },
) as request:
    print(f"PWM running for {DURATION} seconds...")
    start = time.time()
    try:
        while time.time() - start < DURATION:
            request.set_value(GPIO_LINE, Value.ACTIVE)
            time.sleep(t_on)
            request.set_value(GPIO_LINE, Value.INACTIVE)
            time.sleep(t_off)
    finally:
        # This ensures the pin is LOW even if you hit Ctrl+C
        request.set_value(GPIO_LINE, Value.INACTIVE)
        print("GPIO cleared to INACTIVE.")

print("Done.")