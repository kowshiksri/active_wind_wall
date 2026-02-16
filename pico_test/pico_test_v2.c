#include "pico/stdlib.h"
#include "hardware/pwm.h"

#define MOTOR_PIN 15 // Connect your oscilloscope here

int main() {
    // --- 1. SETUP LED ---
    // PICO_DEFAULT_LED_PIN handles the correct LED pin for your board
    const uint LED_PIN = PICO_DEFAULT_LED_PIN; 
    gpio_init(LED_PIN);
    gpio_set_dir(LED_PIN, GPIO_OUT);

    // --- 2. SETUP FIXED PWM ---
    gpio_set_function(MOTOR_PIN, GPIO_FUNC_PWM); 
    uint slice_num = pwm_gpio_to_slice_num(MOTOR_PIN);

    // Divide the 150 MHz system clock by 150 so that 1 tick = 1 microsecond
    pwm_set_clkdiv(slice_num, 150.0f); 

    // Set the total period to 16ms (16000 microseconds). Wrap is period - 1.
    pwm_set_wrap(slice_num, 15999); 

    // Set the default safe output to exactly 1200 microseconds
    pwm_set_chan_level(slice_num, pwm_gpio_to_channel(MOTOR_PIN), 1500); 

    // Turn the PWM generator on
    pwm_set_enabled(slice_num, true); 

    // --- 3. MAIN LOOP ---
    while (true) {
        // Blink the LED every 500ms so you know the board is alive
        gpio_put(LED_PIN, 1);
        sleep_ms(500);
        gpio_put(LED_PIN, 0);
        sleep_ms(500);
    }
}