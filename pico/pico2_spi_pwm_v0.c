#include "pico/stdlib.h"
#include "hardware/pwm.h"
#include "hardware/spi.h"

// === STEP 2: PWM + SPI CONTROL ===
// Motor PWM on GP14 (Physical Pin 19)
#define MOTOR_PIN 14
#define LED_PIN 25

// PWM settings (proven to work)
#define PWM_DIVIDER 64.0f
#define PWM_WRAP    31250

// SPI configuration
#define SPI_INST spi0
#define PIN_MISO 16  // Pin 21
#define PIN_CS   17  // Pin 22
#define PIN_SCK  18  // Pin 24
#define PIN_MOSI 19  // Pin 25

// Simple packet: [START, PWM_HIGH, PWM_LOW, END]
#define PACKET_START 0xAA
#define PACKET_END   0x55
#define PACKET_BYTES 4

// PWM control
uint slice;
uint channel;

void set_motor_pwm_us(uint16_t pulse_us) {
    // Clamp to safe range
    if (pulse_us < 1000) pulse_us = 1000;
    if (pulse_us > 2700) pulse_us = 2700;
    
    // CORRECTED formula: level = pulse_us * 2.34375
    uint16_t level = (uint16_t)(pulse_us * 2.34375f);
    if (level > PWM_WRAP) level = PWM_WRAP;
    
    pwm_set_chan_level(slice, channel, level);
}

int main() {
    // Initialize LED
    gpio_init(LED_PIN);
    gpio_set_dir(LED_PIN, GPIO_OUT);
    gpio_put(LED_PIN, 1);

    // Initialize PWM on motor pin
    gpio_set_function(MOTOR_PIN, GPIO_FUNC_PWM);
    slice = pwm_gpio_to_slice_num(MOTOR_PIN);
    channel = pwm_gpio_to_channel(MOTOR_PIN);

    pwm_set_clkdiv(slice, PWM_DIVIDER);
    pwm_set_wrap(slice, PWM_WRAP);
    pwm_set_enabled(slice, true);
    
    // Set initial PWM (1500 µs)
    set_motor_pwm_us(1500);

    // Initialize SPI as slave
    spi_init(SPI_INST, 1000000);
    spi_set_slave(SPI_INST, true);
    gpio_set_function(PIN_MISO, GPIO_FUNC_SPI);
    gpio_set_function(PIN_CS, GPIO_FUNC_SPI);
    gpio_set_function(PIN_SCK, GPIO_FUNC_SPI);
    gpio_set_function(PIN_MOSI, GPIO_FUNC_SPI);

    uint8_t packet[PACKET_BYTES];
    uint32_t last_blink = 0;

    while (true) {
        // Read SPI if data available (non-blocking check)
        if (spi_is_readable(SPI_INST)) {
            spi_read_blocking(SPI_INST, 0, packet, PACKET_BYTES);
            
            // Validate and apply
            if (packet[0] == PACKET_START && packet[3] == PACKET_END) {
                uint16_t pwm_us = (packet[1] << 8) | packet[2];
                set_motor_pwm_us(pwm_us);
                
                // Quick blink to confirm packet received
                gpio_xor_mask(1u << LED_PIN);
            }
        }
        
        // Slow blink every 500ms to show alive
        uint32_t now = to_ms_since_boot(get_absolute_time());
        if (now - last_blink >= 500) {
            gpio_xor_mask(1u << LED_PIN);
            last_blink = now;
        }
    }
}