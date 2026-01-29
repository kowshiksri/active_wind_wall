import gpiod
import time

GPIO_LINE = 18        # BCM GPIO18 (physical pin 12)
FREQ = 1000           # 1 kHz
DUTY = 0.5
DURATION = 10

period = 1.0 / FREQ
t_on = period * DUTY
t_off = period * (1 - DUTY)

chip = gpiod.Chip("/dev/gpiochip0")

# Request the line (NEW API)
lines = chip.request_lines(
    consumer="pwm-test",
    config={
        GPIO_LINE: gpiod.LineSettings(
            direction=gpiod.LineDirection.OUTPUT,
            output_value=0
        )
    }
)

print("PWM running for 10 seconds...")

start = time.time()
while time.time() - start < DURATION:
    lines.set_value(GPIO_LINE, 1)
    time.sleep(t_on)
    lines.set_value(GPIO_LINE, 0)
    time.sleep(t_off)

lines.set_value(GPIO_LINE, 0)
lines.release()
chip.close()

print("Done.")
