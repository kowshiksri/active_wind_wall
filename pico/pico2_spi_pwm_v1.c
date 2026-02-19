#include "pico/stdlib.h"
#include "hardware/pwm.h"
#include "hardware/spi.h"
#include "hardware/gpio.h"
#include <stdbool.h>

// ==========================================
// CONFIG
// ==========================================
// Change this for each board: 0, 1, 2, 3
#define PICO_ID 0

#define MOTORS_PER_PICO 9
static const uint MOTOR_PINS[MOTORS_PER_PICO] = {0,1,2,3,4,5,6,7,8};

#define LED_PIN 25

// SPI0 on Pico 2 (slave)
#define SPI_INST spi0
#define PIN_MISO 19   // SPI0 TX  (to Pi MISO)   - UNUSED for now
#define PIN_CS   17   // SPI0 CSn (from Pi CE0)
#define PIN_SCK  18   // SPI0 SCK
#define PIN_MOSI 16   // SPI0 RX  (from Pi MOSI)

// Frame parameters
#define TOTAL_MOTORS    36
#define FRAME_BYTES     TOTAL_MOTORS

#define MY_START (PICO_ID * MOTORS_PER_PICO)
#define MY_END   (MY_START + MOTORS_PER_PICO)

// SYNC pin
#define SYNC_PIN 22

// Globals
uint slices[MOTORS_PER_PICO];
uint channels[MOTORS_PER_PICO];

// Latest values for this Pico's 9 motors
volatile uint8_t motor_values[MOTORS_PER_PICO];
volatile uint8_t active_frame_buffer[MOTORS_PER_PICO];

volatile bool sync_pulse_detected = false;
volatile uint32_t sync_counter = 0;

// Global byte index in current 36-byte frame (0..35)
volatile uint8_t byte_index = 0;

// ==========================================
// PWM CONTROL
// ==========================================
void set_motor_pwm_us(uint motor_index, uint16_t pulse_us) {
    if (pulse_us < 1000) pulse_us = 1000;
    if (pulse_us > 2000) pulse_us = 2000;

    // 125 MHz / 64 ~= 1.953125 MHz -> ~2.34375 counts per us
    uint16_t level = (uint16_t)(pulse_us * 2.34375f);
    if (level > 31250) level = 31250;

    pwm_set_chan_level(slices[motor_index], channels[motor_index], level);
}

// ==========================================
// SYNC IRQ
// ==========================================
void sync_irq_handler(uint gpio, uint32_t events) {
    if (gpio == SYNC_PIN) {
        sync_pulse_detected = true;
        sync_counter++;
        if (sync_counter >= 20) {
            gpio_xor_mask(1u << LED_PIN);
            sync_counter = 0;
        }
    }
}

// ==========================================
// MAIN
// ==========================================
int main() {
    stdio_init_all();

    // LED
    gpio_init(LED_PIN);
    gpio_set_dir(LED_PIN, GPIO_OUT);
    gpio_put(LED_PIN, 1);

    // PWM initialisation
    for (uint i = 0; i < MOTORS_PER_PICO; i++) {
        gpio_set_function(MOTOR_PINS[i], GPIO_FUNC_PWM);
        slices[i] = pwm_gpio_to_slice_num(MOTOR_PINS[i]);
        channels[i] = pwm_gpio_to_channel(MOTOR_PINS[i]);

        pwm_set_clkdiv(slices[i], 64.0f);
        pwm_set_wrap(slices[i], 31250);
        pwm_set_enabled(slices[i], true);

        motor_values[i] = 0;
        active_frame_buffer[i] = 0;
        set_motor_pwm_us(i, 1000);   // idle
    }

    // SPI slave setup
    spi_init(SPI_INST, 1000000);        // baud ignored in slave mode
    spi_set_slave(SPI_INST, true);
    gpio_set_function(PIN_MISO, GPIO_FUNC_SPI);
    gpio_set_function(PIN_CS,   GPIO_FUNC_SPI);
    gpio_set_function(PIN_SCK,  GPIO_FUNC_SPI);
    gpio_set_function(PIN_MOSI, GPIO_FUNC_SPI);

    // SYNC pin
    gpio_init(SYNC_PIN);
    gpio_set_dir(SYNC_PIN, GPIO_IN);
    gpio_pull_down(SYNC_PIN);
    gpio_set_irq_enabled_with_callback(SYNC_PIN, GPIO_IRQ_EDGE_RISE, true, &sync_irq_handler);

    absolute_time_t last_sync_time = get_absolute_time();
    const uint64_t SAFETY_TIMEOUT_US = 200000; // 200 ms

    while (true) {
        // A. SPI RX: one byte at a time, count bytes in frame
        while (spi_is_readable(SPI_INST)) {
            uint8_t rx = (uint8_t)spi_get_hw(SPI_INST)->dr;

            uint8_t idx = byte_index;
            if (byte_index < FRAME_BYTES) {
                byte_index++;
            } else {
                // extra bytes beyond 36 are ignored until next SYNC
            }

            if (idx >= MY_START && idx < MY_END) {
                motor_values[idx - MY_START] = rx;
            }
        }

        // B. On SYNC: latch values + apply PWM, then reset byte counter
        if (sync_pulse_detected) {
            sync_pulse_detected = false;
            last_sync_time = get_absolute_time();

            // Snapshot latest 9 values
            for (uint i = 0; i < MOTORS_PER_PICO; i++) {
                active_frame_buffer[i] = motor_values[i];
            }

            // Apply PWM for this frame
            for (uint i = 0; i < MOTORS_PER_PICO; i++) {
                uint8_t raw_val = active_frame_buffer[i];

                uint16_t target_pwm;
                if (raw_val == 0) {
                    target_pwm = 1000;
                } else {
                    target_pwm = 1200 + ((uint32_t)raw_val * 800) / 255;
                }
                if (target_pwm > 2000) target_pwm = 2000;
                set_motor_pwm_us(i, target_pwm);
            }

            // Reset byte counter for next 36-byte frame
            byte_index = 0;
        }

        // C. Safety watchdog
        if (absolute_time_diff_us(last_sync_time, get_absolute_time()) > SAFETY_TIMEOUT_US) {
            for (uint i = 0; i < MOTORS_PER_PICO; i++) {
                set_motor_pwm_us(i, 1000);
            }
            gpio_put(LED_PIN, (to_ms_since_boot(get_absolute_time()) % 200) < 100);
        }
    }
}
