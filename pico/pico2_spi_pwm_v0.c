#include "pico/stdlib.h"
#include "hardware/pwm.h"
#include "hardware/spi.h"
#include <stdbool.h>

// === STEP 2: PWM + SPI CONTROL ===
// Motor PWM pins (9 motors per Pico)
#define MOTORS_PER_PICO 9
static const uint MOTOR_PINS[MOTORS_PER_PICO] = {0, 1, 2, 3, 4, 5, 6, 7, 8};
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

// Broadcast frame configuration
#define PICO_ID 0
#define TOTAL_MOTORS 36
#define BYTES_PER_MOTOR 2
#define FRAME_BYTES (1 + (TOTAL_MOTORS * BYTES_PER_MOTOR) + 1)
#define OFFSET (1 + (PICO_ID * MOTORS_PER_PICO * BYTES_PER_MOTOR))

// Sync (latch) pin
#define SYNC_PIN 22

// PWM control
uint slices[MOTORS_PER_PICO];
uint channels[MOTORS_PER_PICO];

volatile uint8_t next_frame_buffer[MOTORS_PER_PICO * BYTES_PER_MOTOR];
volatile bool sync_pulse = false;

void set_motor_pwm_us(uint motor_index, uint16_t pulse_us) {
    // Clamp to safe range
    if (pulse_us < 1000) pulse_us = 1000;
    if (pulse_us > 2700) pulse_us = 2700;
    
    // CORRECTED formula: level = pulse_us * 2.34375
    uint16_t level = (uint16_t)(pulse_us * 2.34375f);
    if (level > PWM_WRAP) level = PWM_WRAP;
    
    pwm_set_chan_level(slices[motor_index], channels[motor_index], level);
}

void apply_next_frame(void) {
    for (uint i = 0; i < MOTORS_PER_PICO; i++) {
        uint16_t pwm_us = ((uint16_t)next_frame_buffer[i * 2] << 8) |
                          (uint16_t)next_frame_buffer[i * 2 + 1];
        set_motor_pwm_us(i, pwm_us);
    }
}

void sync_irq_handler(uint gpio, uint32_t events) {
    if (gpio == SYNC_PIN && (events & GPIO_IRQ_EDGE_RISE)) {
        sync_pulse = true;
    }
}

int main() {
    // Initialize LED
    gpio_init(LED_PIN);
    gpio_set_dir(LED_PIN, GPIO_OUT);
    gpio_put(LED_PIN, 1);

    // Initialize PWM on motor pins
    for (uint i = 0; i < MOTORS_PER_PICO; i++) {
        gpio_set_function(MOTOR_PINS[i], GPIO_FUNC_PWM);
        slices[i] = pwm_gpio_to_slice_num(MOTOR_PINS[i]);
        channels[i] = pwm_gpio_to_channel(MOTOR_PINS[i]);

        pwm_set_clkdiv(slices[i], PWM_DIVIDER);
        pwm_set_wrap(slices[i], PWM_WRAP);
        pwm_set_enabled(slices[i], true);

        // Set initial PWM (1500 µs)
        set_motor_pwm_us(i, 1500);
    }

    // Initialize SPI as slave
    spi_init(SPI_INST, 1000000);
    spi_set_slave(SPI_INST, true);
    gpio_set_function(PIN_MISO, GPIO_FUNC_SPI);
    gpio_set_function(PIN_CS, GPIO_FUNC_SPI);
    gpio_set_function(PIN_SCK, GPIO_FUNC_SPI);
    gpio_set_function(PIN_MOSI, GPIO_FUNC_SPI);

    // Configure sync (latch) pin interrupt
    gpio_init(SYNC_PIN);
    gpio_set_dir(SYNC_PIN, GPIO_IN);
    gpio_pull_down(SYNC_PIN);
    gpio_set_irq_enabled_with_callback(SYNC_PIN, GPIO_IRQ_EDGE_RISE, true, &sync_irq_handler);

    uint32_t last_blink = 0;
    bool in_frame = false;
    uint16_t frame_index = 0;

    while (true) {
        // Read SPI if data available (non-blocking check)
        if (spi_is_readable(SPI_INST)) {
            uint8_t rx;
            spi_read_blocking(SPI_INST, 0, &rx, 1);

            if (!in_frame) {
                if (rx == PACKET_START) {
                    in_frame = true;
                    frame_index = 1; // Next byte index in frame
                }
            } else {
                if (rx == PACKET_START) {
                    frame_index = 1;
                } else {
                    if (frame_index >= OFFSET && frame_index < (OFFSET + (MOTORS_PER_PICO * BYTES_PER_MOTOR))) {
                        next_frame_buffer[frame_index - OFFSET] = rx;
                    }

                    if (frame_index == (FRAME_BYTES - 1)) {
                        if (rx == PACKET_END) {
                            // Quick blink to confirm packet received
                            gpio_xor_mask(1u << LED_PIN);
                        }
                        in_frame = false;
                        frame_index = 0;
                    } else {
                        frame_index++;
                    }
                }
            }
        }

        if (sync_pulse) {
            sync_pulse = false;
            apply_next_frame();
        }
        
        // Slow blink every 500ms to show alive
        uint32_t now = to_ms_since_boot(get_absolute_time());
        if (now - last_blink >= 500) {
            gpio_xor_mask(1u << LED_PIN);
            last_blink = now;
        }
    }
}