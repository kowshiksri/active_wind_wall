#include "pico/stdlib.h"
#include "hardware/pwm.h"
#include "hardware/spi.h"
#include "hardware/gpio.h"

// ==========================================
// CONFIGURATION
// ==========================================
#define PICO_ID 0   
#define MOTORS_PER_PICO 9
static const uint MOTOR_PINS[MOTORS_PER_PICO] = {0, 1, 2, 3, 4, 5, 6, 7, 8};
#define LED_PIN 25

#define PWM_DIVIDER 64.0f
#define PWM_WRAP    31250

#define SPI_INST spi0
#define PIN_CS   17 
#define PIN_SCK  18 
#define PIN_MOSI 16 
// CRITICAL: MISO PIN REMOVED. Slaves must not drive the MISO line on a shared bus!

#define TOTAL_MOTORS 36

uint slices[MOTORS_PER_PICO];
uint channels[MOTORS_PER_PICO];

// ==========================================
// PWM CONTROL
// ==========================================
void set_motor_pwm_us(uint motor_index, uint16_t pulse_us) {
    if (pulse_us < 1000) pulse_us = 1000;
    if (pulse_us > 2000) pulse_us = 2000;
    
    // (pulse_us * 125MHz) / (64 * 1000000) = pulse_us * 1.953125
    uint16_t level = (uint16_t)(pulse_us * 1.953125f);
    if (level > PWM_WRAP) level = PWM_WRAP;
    
    pwm_set_chan_level(slices[motor_index], channels[motor_index], level);
}

// ==========================================
// MAIN
// ==========================================
int main() {
    gpio_init(LED_PIN);
    gpio_set_dir(LED_PIN, GPIO_OUT);
    gpio_put(LED_PIN, 1);

    for (uint i = 0; i < MOTORS_PER_PICO; i++) {
        gpio_set_function(MOTOR_PINS[i], GPIO_FUNC_PWM);
        slices[i] = pwm_gpio_to_slice_num(MOTOR_PINS[i]);
        channels[i] = pwm_gpio_to_channel(MOTOR_PINS[i]);

        pwm_set_clkdiv(slices[i], PWM_DIVIDER);
        pwm_set_wrap(slices[i], PWM_WRAP);
        pwm_set_enabled(slices[i], true);
        set_motor_pwm_us(i, 1000); 
    }

    // Initialize SPI
    spi_init(SPI_INST, 1000000);
    spi_set_slave(SPI_INST, true);
    
    // Explicitly enforce Mode 0 (Match this in Python!)
    spi_set_format(SPI_INST, 8, SPI_CPOL_0, SPI_CPHA_0, SPI_MSB_FIRST);

    // ONLY initialize RX pins. Do not initialize MISO.
    gpio_set_function(PIN_CS,   GPIO_FUNC_SPI);
    gpio_set_function(PIN_SCK,  GPIO_FUNC_SPI);
    gpio_set_function(PIN_MOSI, GPIO_FUNC_SPI);

    uint8_t frame_buffer[TOTAL_MOTORS];
    const int MY_START = PICO_ID * MOTORS_PER_PICO;

    while (true) {
        // 1. HARDWARE BLOCKING: Halt CPU until exactly 36 bytes are clocked in by the Pi.
        // This acts exactly like the working test code you provided. No drops, no shifting.
        spi_read_blocking(SPI_INST, 0, frame_buffer, TOTAL_MOTORS);

        // 2. APPLY: Only process the 9 bytes that belong to this specific Pico
        for (uint i = 0; i < MOTORS_PER_PICO; i++) {
            uint8_t raw_val = frame_buffer[MY_START + i];
            
            uint16_t target_pwm;
            if (raw_val == 0) {
                target_pwm = 1000;
            } else {
                target_pwm = 1200 + ((uint32_t)raw_val * 800) / 255;
            }
            
            set_motor_pwm_us(i, target_pwm);
        }
        
        // Blink LED rapidly to confirm successful frames are arriving
        gpio_xor_mask(1u << LED_PIN);
    }
}