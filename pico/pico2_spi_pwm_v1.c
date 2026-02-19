#include "pico/stdlib.h"
#include "hardware/pwm.h"
#include "hardware/spi.h"
#include "hardware/gpio.h"
#include <stdbool.h>

// ==========================================
// CONFIGURATION
// ==========================================
// CHANGE THIS FOR EACH PICO (0, 1, 2, or 3)
#define PICO_ID 0

// Motor PWM pins (9 motors per Pico)
#define MOTORS_PER_PICO 9
static const uint MOTOR_PINS[MOTORS_PER_PICO] = {0, 1, 2, 3, 4, 5, 6, 7, 8};

#define LED_PIN 25

// PWM settings
#define PWM_DIVIDER 64.0f
#define PWM_WRAP    31250

// SPI configuration
#define SPI_INST spi0
#define PIN_MISO 19
#define PIN_CS   17
#define PIN_SCK  18
#define PIN_MOSI 16

// Frame configuration
#define FRAME_BYTES   36      // 36 motors -> 36 bytes
#define TOTAL_MOTORS  36
#define BYTES_PER_MOTOR 1

// Byte positions for this Pico's motors in the 36-byte frame
#define MY_START (PICO_ID * MOTORS_PER_PICO)             // inclusive
#define MY_END   (MY_START + MOTORS_PER_PICO)            // exclusive

// Sync (latch) pin
#define SYNC_PIN 22

// Globals
uint slices[MOTORS_PER_PICO];
uint channels[MOTORS_PER_PICO];

// Latest full 36-byte frame from SPI
static uint8_t frame_buffer[FRAME_BYTES];
static int     frame_index = 0;
static volatile bool frame_complete = false;

// Per-Pico motor values (latched on SYNC)
volatile uint8_t active_frame_buffer[MOTORS_PER_PICO];

volatile bool sync_pulse_detected = false;
volatile uint32_t sync_counter = 0;

// ==========================================
// PWM CONTROL
// ==========================================
void set_motor_pwm_us(uint motor_index, uint16_t pulse_us) {
    if (pulse_us < 1000) pulse_us = 1000;
    if (pulse_us > 2000) pulse_us = 2000;

    // 125 MHz / 64 ~= 1.953125 MHz -> 1 us ~ 1.953125 counts
    uint16_t level = (uint16_t)(pulse_us * 2.34375f);
    if (level > PWM_WRAP) level = PWM_WRAP;

    pwm_set_chan_level(slices[motor_index], channels[motor_index], level);
}

// ==========================================
// INTERRUPT HANDLER
// ==========================================
void sync_irq_handler(uint gpio, uint32_t events) {
    if (gpio == SYNC_PIN) {
        sync_pulse_detected = true;

        // Simple heartbeat: toggle LED every 20 sync pulses
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
    stdio_init_all(); // optional, for USB debug if available

    // 1. Initialize LED
    gpio_init(LED_PIN);
    gpio_set_dir(LED_PIN, GPIO_OUT);
    gpio_put(LED_PIN, 1);

    // 2. Initialize PWM
    for (uint i = 0; i < MOTORS_PER_PICO; i++) {
        gpio_set_function(MOTOR_PINS[i], GPIO_FUNC_PWM);
        slices[i] = pwm_gpio_to_slice_num(MOTOR_PINS[i]);
        channels[i] = pwm_gpio_to_channel(MOTOR_PINS[i]);

        pwm_set_clkdiv(slices[i], PWM_DIVIDER);
        pwm_set_wrap(slices[i], PWM_WRAP);
        pwm_set_enabled(slices[i], true);

        // DEFAULT: 1000us (IDLE/ARMED)
        set_motor_pwm_us(i, 1000);
        active_frame_buffer[i] = 0;
    }

    // 3. Initialize SPI (Slave)
    spi_init(SPI_INST, 1000000);    // baud ignored in slave mode
    spi_set_slave(SPI_INST, true);
    gpio_set_function(PIN_MISO, GPIO_FUNC_SPI);
    gpio_set_function(PIN_CS,   GPIO_FUNC_SPI);
    gpio_set_function(PIN_SCK,  GPIO_FUNC_SPI);
    gpio_set_function(PIN_MOSI, GPIO_FUNC_SPI);

    // 4. Initialize Sync Pin
    gpio_init(SYNC_PIN);
    gpio_set_dir(SYNC_PIN, GPIO_IN);
    gpio_pull_down(SYNC_PIN);
    gpio_set_irq_enabled_with_callback(SYNC_PIN, GPIO_IRQ_EDGE_RISE, true, &sync_irq_handler);

    // Timing / safety
    absolute_time_t last_sync_time = get_absolute_time();
    const uint64_t SAFETY_TIMEOUT_US = 200000;   // 200 ms -> fail-safe

    while (true) {
        // --- A. SPI RECEIVE: continuously fill 36-byte frame_buffer ---
        while (spi_is_readable(SPI_INST)) {
            uint8_t rx = (uint8_t)spi_get_hw(SPI_INST)->dr;

            frame_buffer[frame_index] = rx;
            frame_index++;

            if (frame_index >= FRAME_BYTES) {
                frame_index = 0;
                frame_complete = true;  // We have at least one full frame
            }
        }

        // --- B. On SYNC: use latest complete frame & preload TX FIFO ---
        if (sync_pulse_detected && frame_complete) {
            sync_pulse_detected = false;
            frame_complete = false;
            last_sync_time = get_absolute_time();

            // 1) Copy this Pico's bytes from frame_buffer into active_frame_buffer
            for (uint i = 0; i < MOTORS_PER_PICO; i++) {
                uint idx = MY_START + i;   // 0..35
                active_frame_buffer[i] = frame_buffer[idx];
            }

            // 2) DEBUG: preload our 9 motor bytes into SPI TX FIFO
            //    so the Pi can read them back in the next transfer.
            for (uint i = 0; i < MOTORS_PER_PICO; i++) {
                // Wait until TX FIFO has space
                while (!spi_is_writable(SPI_INST)) {
                    tight_loop_contents();
                }
                spi_get_hw(SPI_INST)->dr = active_frame_buffer[i];
            }

            // 3) Apply PWM from active_frame_buffer
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
        }

        // --- C. SAFETY WATCHDOG: if no sync for 200 ms, go to idle ---
        if (absolute_time_diff_us(last_sync_time, get_absolute_time()) > SAFETY_TIMEOUT_US) {
            for (uint i = 0; i < MOTORS_PER_PICO; i++) {
                set_motor_pwm_us(i, 1000);
            }
            gpio_put(LED_PIN, (to_ms_since_boot(get_absolute_time()) % 200) < 100);
        }
    }
}
