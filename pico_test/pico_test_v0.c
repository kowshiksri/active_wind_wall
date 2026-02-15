#include "pico/stdlib.h"

int main() {
    // Initialize GPIO pin 25 (LED) as output
    const uint LED_PIN = 25;
    gpio_init(LED_PIN);
    gpio_set_dir(LED_PIN, GPIO_OUT);

    // Blink the LED every second
    while (true) {
        gpio_put(LED_PIN, 1); // Turn on LED
        sleep_ms(1000);       // Wait for 1 second
        gpio_put(LED_PIN, 0); // Turn off LED
        sleep_ms(1000);       // Wait for 1 second
    }

    return 0;
}