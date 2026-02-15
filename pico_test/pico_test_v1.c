#include "pico/stdlib.h"
#include "hardware/pwm.h"

#define MOTOR_PIN 14

// simple test to verify PWM output on a single pin (GP14) and flash LED (GP25) to indicate the program is running
#define LED_PIN 25
int main() {
    // 1. Tell the GPIO pin to act as a PWM output
    gpio_set_function(MOTOR_PIN, GPIO_FUNC_PWM);
    
    // 2. Find out which hardware PWM slice controls this pin
    uint slice_num = pwm_gpio_to_slice_num(MOTOR_PIN);

    // 3. Set the frequency to 1 kHz
    // Assuming a 150MHz system clock: 150,000,000 / (6.0 * 25000) = 1000 Hz
    pwm_set_clkdiv(slice_num, 6.0f);
    pwm_set_wrap(slice_num, 24999);

    // 4. Set a fixed duty cycle. 
    // Let's set it to 50% (12500 out of 25000)
    pwm_set_chan_level(slice_num, pwm_gpio_to_channel(MOTOR_PIN), 12500);
    
    // 5. Turn it on
    pwm_set_enabled(slice_num, true);

    // Flash the LED to indicate the program is running
    gpio_init(LED_PIN);
    gpio_set_dir(LED_PIN, GPIO_OUT);

    while (true) {
        // Do nothing, the hardware PWM runs by itself in the background
        tight_loop_contents();
        gpio_put(LED_PIN, 1); // Turn on LED
        sleep_ms(1000);       // Wait for 1 second
        gpio_put(LED_PIN, 0); // Turn off LED
        sleep_ms(1000);       // Wait for 1 second
    }
}