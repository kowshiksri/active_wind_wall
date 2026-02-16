#include "pico/stdlib.h"
#include "hardware/pwm.h"
#include "hardware/spi.h"

#define MOTOR_PIN 15
// SPI0 Pin Definitions (Default for Pico)
#define SPI_PORT spi0
#define PIN_RX  16 // Connect to Pi5 MOSI
#define PIN_CSN 17 // Connect to Pi5 CE0
#define PIN_SCK 18 // Connect to Pi5 SCLK

// Safety Constants
#define PWM_MIN 1000
#define PWM_MAX 2000
#define PWM_DEFAULT 1500
#define TIMEOUT_US 100000 // 100ms timeout for safety

int main() {
    // --- 1. SETUP LED ---
    const uint LED_PIN = PICO_DEFAULT_LED_PIN;
    gpio_init(LED_PIN);
    gpio_set_dir(LED_PIN, GPIO_OUT);

    // --- 2. SETUP PWM (Your original config) ---
    gpio_set_function(MOTOR_PIN, GPIO_FUNC_PWM);
    uint slice_num = pwm_gpio_to_slice_num(MOTOR_PIN);
    pwm_set_clkdiv(slice_num, 150.0f); // 1 tick = 1us
    pwm_set_wrap(slice_num, 15999);    // 16ms period
    pwm_set_chan_level(slice_num, pwm_gpio_to_channel(MOTOR_PIN), PWM_DEFAULT);
    pwm_set_enabled(slice_num, true);

    // --- 3. SETUP SPI SLAVE ---
    // Initialize SPI at 1MHz (Slave follows Master clock anyway)
    spi_init(SPI_PORT, 1000 * 1000);
    spi_set_slave(SPI_PORT, true);
    
    // Assign SPI functions to pins
    gpio_set_function(PIN_RX, GPIO_FUNC_SPI);
    gpio_set_function(PIN_CSN, GPIO_FUNC_SPI);
    gpio_set_function(PIN_SCK, GPIO_FUNC_SPI);

    // Variables for non-blocking loop
    uint64_t last_msg_time = 0;
    uint64_t last_led_time = 0;
    bool led_state = false;
    uint8_t received_val = 0;

    // --- 4. MAIN LOOP ---
    while (true) {
        // A. Check for SPI Data (Non-blocking)
        if (spi_is_readable(SPI_PORT)) {
            // Read 1 byte from the buffer
            spi_read_blocking(SPI_PORT, 0, &received_val, 1);
            
            // Map 0-255 (Byte) -> 1000-2000 (Microseconds)
            // Formula: 1000 + (value * 1000 / 255)
            uint16_t new_pwm = PWM_MIN + ((uint32_t)received_val * (PWM_MAX - PWM_MIN)) / 255;
            
            pwm_set_chan_level(slice_num, pwm_gpio_to_channel(MOTOR_PIN), new_pwm);
            last_msg_time = time_us_64(); // Update watchdog timer
        }

        // B. Safety Watchdog
        // If no data received for TIMEOUT_US, revert to Safe Default
        if (time_us_64() - last_msg_time > TIMEOUT_US) {
            pwm_set_chan_level(slice_num, pwm_gpio_to_channel(MOTOR_PIN), PWM_DEFAULT);
        }

        // C. Blink LED (Non-blocking)
        // Replaces sleep_ms(500) to allow fast SPI reading
        if (time_us_64() - last_led_time > 500000) {
            led_state = !led_state;
            gpio_put(LED_PIN, led_state);
            last_led_time = time_us_64();
        }
    }
}