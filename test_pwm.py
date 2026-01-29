from gpiozero import PWMOutputDevice
from time import sleep

# GPIO18 = physical pin 12
pwm = PWMOutputDevice(18, frequency=1000)

print("PWM ON (1 kHz, 50% duty) for 10 seconds")
pwm.value = 0.5   # 50% duty cycle
sleep(10)

print("PWM OFF")
pwm.off()
