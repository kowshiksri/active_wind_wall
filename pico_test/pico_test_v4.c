#include "pico/stdlib.h"
#include "hardware/pwm.h"
#include "hardware/spi.h"

#define MOTOR_PIN 15
#define SPI_PORT spi0
#define PIN_RX  16 
#define PIN_CSN 17 
#define PIN_SCK 18 

#define MY_PICO_ID  0x01 
#define SYNC_ID     0xFF 

// PWM Config
#define PWM_MIN 1000
#define PWM_MAX 2000
#define PWM_DEFAULT 1500

int main() {
    // 1. SETUP LED
    const uint LED_PIN = PICO_DEFAULT_LED_PIN; 
    gpio_init(LED_PIN); gpio_set_dir(LED_PIN, GPIO_OUT);

    // 2. SETUP PWM
    gpio_set_function(MOTOR_PIN, GPIO_FUNC_PWM); 
    uint slice_num = pwm_gpio_to_slice_num(MOTOR_PIN);
    pwm_set_clkdiv(slice_num, 150.0f); 
    pwm_set_wrap(slice_num, 15999); 
    pwm_set_chan_level(slice_num, pwm_gpio_to_channel(MOTOR_PIN), PWM_DEFAULT); 
    pwm_set_enabled(slice_num, true); 

    // 3. SETUP SPI SLAVE
    spi_init(SPI_PORT, 1000 * 1000);
    spi_set_slave(SPI_PORT, true);
    gpio_set_function(PIN_RX, GPIO_FUNC_SPI);
    gpio_set_function(PIN_CSN, GPIO_FUNC_SPI);
    gpio_set_function(PIN_SCK, GPIO_FUNC_SPI);

    // Data Buffers
    uint8_t rx_buffer[2]; 
    uint16_t pending_pwm = PWM_DEFAULT;
    
    // Heartbeat Timers
    uint64_t last_heartbeat = 0;
    bool led_state = false;

    while (true) {
        // --- A. READ SPI (Non-blocking check) ---
        // We only read if 2 bytes are actually available in the buffer
        if (spi_is_readable(SPI_PORT) >= 2) {
            spi_read_blocking(SPI_PORT, 0, rx_buffer, 2);

            uint8_t addr = rx_buffer[0];
            uint8_t data = rx_buffer[1];

            // 1. Store Data
            if (addr == MY_PICO_ID) {
                pending_pwm = PWM_MIN + ((uint32_t)data * (PWM_MAX - PWM_MIN)) / 255;
            }

            // 2. Sync Trigger
            if (addr == SYNC_ID) {
                pwm_set_chan_level(slice_num, pwm_gpio_to_channel(MOTOR_PIN), pending_pwm);
                
                // VISUAL FEEDBACK: Force LED toggle immediately on sync
                led_state = !led_state;
                gpio_put(LED_PIN, led_state);
            }
        }

        // --- B. HEARTBEAT (If no data is coming, blink slowly) ---
        // This confirms the board is powered and loop is running
        uint64_t now = time_us_64();
        if (now - last_heartbeat > 500000) { // Every 500ms
             // Only blink if we haven't toggled recently from a Sync
             // (This creates a "nervous" blink when data flows, slow blink when idle)
             led_state = !led_state;
             gpio_put(LED_PIN, led_state);
             last_heartbeat = now;
        }
    }
}