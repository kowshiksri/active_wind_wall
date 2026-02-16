#include "pico/stdlib.h"
#include "hardware/pwm.h"
#include "hardware/spi.h"

#define MOTOR_PIN 15
#define SPI_PORT spi0
#define PIN_RX  16 
#define PIN_CSN 17 
#define PIN_SCK 18 

// --- CONFIGURATION ---
// Change this for each Pico (0x01, 0x02, 0x03, 0x04)
#define MY_PICO_ID  0x01 
#define SYNC_ID     0xFF  // The "Go" signal for everyone

// PWM Limits
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

    // 4. DATA BUFFERS
    uint8_t rx_buffer[2];   // We expect [Address, Value]
    uint16_t pending_pwm = PWM_DEFAULT; // "Shadow" buffer (Waiting for trigger)

    while (true) {
        // We now wait for 2 bytes: [Address, Data]
        if (spi_is_readable(SPI_PORT) >= 2) {
            spi_read_blocking(SPI_PORT, 0, rx_buffer, 2);

            uint8_t addr = rx_buffer[0];
            uint8_t data = rx_buffer[1];

            // CASE A: Addressed to ME? -> Store it, don't show it.
            if (addr == MY_PICO_ID) {
                // Convert 0-255 to 1000-2000us
                pending_pwm = PWM_MIN + ((uint32_t)data * (PWM_MAX - PWM_MIN)) / 255;
            }

            // CASE B: Is it the SYNC signal? -> Apply the stored value.
            if (addr == SYNC_ID) {
                pwm_set_chan_level(slice_num, pwm_gpio_to_channel(MOTOR_PIN), pending_pwm);
                
                // Toggle LED on Sync so we can see it's working
                gpio_put(LED_PIN, !gpio_get(LED_PIN)); 
            }
        }
    }
}