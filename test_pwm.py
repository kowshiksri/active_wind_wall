import gpiod
import time

GPIO_LINE = 18        # BCM GPIO18
FREQ = 1000           # 1 kHz
DUTY = 0.5            # 50%
DURATION = 10         # seconds

period = 1.0 / FREQ
t_on = period * DUTY
t_off = period * (1 - DUTY)

# Open GPIO chip
chip = gpiod.Chip("gpiochip0")
line = chip.get_line(GPIO_LINE)

# Request line as output
line.request(
    consumer="pwm-test",
    type=gpiod.LINE_REQ_DIR_OUT,
    default_vals=[0]
)

print("PWM running (1 kHz, 50%) for 10 seconds...")

start = time.time()
while time.time() - start < DURATION:
    line.set_value(1)
    time.sleep(t_on)
    line.set_value(0)
    time.sleep(t_off)

# Cleanup
line.set_value(0)
line.release()
chip.close()

print("Done.")
