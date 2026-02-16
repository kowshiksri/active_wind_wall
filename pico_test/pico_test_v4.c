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

    // Simple State Machine variables
    bool waiting_for_data = false;

    while (true) {
        // Only check if data is actually there
        if (spi_is_readable(SPI_PORT)) {
            
            // 1. Read ONE byte only
            uint8_t received_byte = 0;
            spi_read_blocking(SPI_PORT, 0, &received_byte, 1);

            // 2. Logic: What is this byte?
            if (waiting_for_data) {
                // If we were waiting for data, THIS is the data
                // Map 0-255 -> 1000-2000us
                pending_pwm = PWM_MIN + ((uint32_t)received_byte * (PWM_MAX - PWM_MIN)) / 255;
                
                // Reset state to wait for next Address
                waiting_for_data = false;
                
            } else {
                // We are idle. Is this an Address or a Sync?
                
                if (received_byte == MY_PICO_ID) {
                    // Valid Address! The NEXT byte will be data.
                    waiting_for_data = true;
                }
                
                else if (received_byte == SYNC_ID) {
                    // SYNC! Apply the shadow value to the motor
                    pwm_set_chan_level(slice_num, pwm_gpio_to_channel(MOTOR_PIN), pending_pwm);
                    
                    // Flash LED rapidly to show we got a Sync
                    gpio_put(LED_PIN, !gpio_get(LED_PIN)); 
                }
                
                // If it's neither (noise or wrong ID), we just ignore it 
                // and loop back to catch the next real byte.
            }
        }

        // Keep the heartbeat alive (1Hz)
        uint64_t now = time_us_64();
        if (now - last_heartbeat > 500000) {
             gpio_put(LED_PIN, !gpio_get(LED_PIN));
             last_heartbeat = now;
        }
    }
}