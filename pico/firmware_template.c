#include "pico/stdlib.h"
#include "hardware/pwm.h"
#include "hardware/spi.h"
#include "hardware/gpio.h"
#include <stdbool.h>

// ==========================================
// CONFIGURATION
// ==========================================

// Board identifier — change for each Pico (0, 1, 2, or 3)
#define PICO_ID {{PICO_ID}}

#define MOTORS_PER_PICO 9
static const uint MOTOR_PINS[MOTORS_PER_PICO] = {0, 1, 2, 3, 4, 5, 6, 7, 8};

#define LED_PIN 25

// SPI (slave)
#define SPI_INST spi0
#define PIN_MISO 19
#define PIN_CS   17   // CS rising edge = transaction complete = apply PWM
#define PIN_SCK  18
#define PIN_MOSI 16

// Frame: 36 bytes broadcast to all Picos, each Pico takes its 9
#define TOTAL_MOTORS 36
#define FRAME_BYTES  TOTAL_MOTORS
#define MY_START     (PICO_ID * MOTORS_PER_PICO)
#define MY_END       (MY_START + MOTORS_PER_PICO)

// ==========================================
// GLOBAL STATE
// ==========================================

uint slices[MOTORS_PER_PICO];
uint channels[MOTORS_PER_PICO];

static uint8_t  rx_buffer[FRAME_BYTES]; // single receive buffer — no double buffering
volatile uint8_t  byte_index = 0;
volatile bool     cs_rise_detected = false;
volatile uint32_t frame_counter = 0;

// ==========================================
// PWM CONTROL
// ==========================================
void set_motor_pwm_us(uint motor_index, uint16_t pulse_us) {
    // 0 = no pulse (disarmed)
    if (pulse_us == 0) {
        pwm_set_chan_level(slices[motor_index], channels[motor_index], 0);
        return;
    }
    if (pulse_us < 1000) pulse_us = 1000;
    if (pulse_us > 2000) pulse_us = 2000;
    // 1 tick = 1 µs (clkdiv=125, wrap=20000 → 50 Hz)
    pwm_set_chan_level(slices[motor_index], channels[motor_index], pulse_us);
}

// ==========================================
// CS INTERRUPT HANDLER
// ==========================================
// Fires on CS rising edge — Pi deasserted CS = full 36-byte frame sent.
// GPIO IRQs fire at pad level regardless of function select (RP2040 §2.19.2)
// so this works even though PIN_CS is configured as GPIO_FUNC_SPI.
void cs_irq_handler(uint gpio, uint32_t events) {
    if (gpio == PIN_CS) {
        cs_rise_detected = true;

        // Blink LED every 20 frames as activity indicator
        frame_counter++;
        if (frame_counter >= 20) {
            gpio_xor_mask(1u << LED_PIN);
            frame_counter = 0;
        }
    }
}

// ==========================================
// MAIN PROGRAM
// ==========================================
int main() {
    stdio_init_all();

    // Status LED on at boot
    gpio_init(LED_PIN);
    gpio_set_dir(LED_PIN, GPIO_OUT);
    gpio_put(LED_PIN, 1);

    // ── PWM init ──────────────────────────────────────────────────────────────
    // Phase 1: configure all slices before enabling (shared slice fix)
    uint32_t slice_mask = 0;
    for (uint i = 0; i < MOTORS_PER_PICO; i++) {
        gpio_set_function(MOTOR_PINS[i], GPIO_FUNC_PWM);
        slices[i]   = pwm_gpio_to_slice_num(MOTOR_PINS[i]);
        channels[i] = pwm_gpio_to_channel(MOTOR_PINS[i]);

        if (!(slice_mask & (1u << slices[i]))) {
            pwm_set_clkdiv(slices[i], 125.0f); // 125 MHz / 125 = 1 MHz = 1 µs/tick
            pwm_set_wrap(slices[i], 20000);     // 20 000 µs = 20 ms = 50 Hz
        }
        slice_mask |= (1u << slices[i]);

        pwm_set_chan_level(slices[i], channels[i], 0); // no pulse until first frame
    }

    // Phase 2: enable all slices simultaneously
    pwm_set_mask_enabled(slice_mask);

    // ── SPI slave init ────────────────────────────────────────────────────────
    spi_init(SPI_INST, 1000000);
    spi_set_slave(SPI_INST, true);
    gpio_set_function(PIN_MISO, GPIO_FUNC_SPI);
    gpio_set_function(PIN_SCK,  GPIO_FUNC_SPI);
    gpio_set_function(PIN_MOSI, GPIO_FUNC_SPI);
    gpio_set_function(PIN_CS,   GPIO_FUNC_SPI);

    // ── CS rising-edge IRQ ───────────────────────────────────────────────────
    // Pi deasserts CS after sending all 36 bytes → this fires → apply PWM.
    // Replaces the separate SYNC pin used in the previous architecture.
    gpio_set_irq_enabled_with_callback(PIN_CS, GPIO_IRQ_EDGE_RISE, true, &cs_irq_handler);

    // ── Main loop ─────────────────────────────────────────────────────────────
    while (true) {

        // === Step A: Drain SPI FIFO into rx_buffer ===
        while (spi_is_readable(SPI_INST)) {
            uint8_t rx = (uint8_t)spi_get_hw(SPI_INST)->dr;
            if (byte_index < FRAME_BYTES) {
                rx_buffer[byte_index++] = rx;
            }
            // bytes beyond 36 are silently dropped
        }

        // === Step B: CS rose → frame complete → apply PWM ===
        if (cs_rise_detected) {
            cs_rise_detected = false;

            // Final FIFO drain — catch any bytes that arrived between
            // the last Step A and the CS rising edge
            while (spi_is_readable(SPI_INST)) {
                uint8_t rx = (uint8_t)spi_get_hw(SPI_INST)->dr;
                if (byte_index < FRAME_BYTES) {
                    rx_buffer[byte_index++] = rx;
                }
            }

            // Apply PWM for this Pico's 9 motors
            for (uint i = 0; i < MOTORS_PER_PICO; i++) {
                uint8_t raw_val = rx_buffer[MY_START + i];

                uint16_t target_pwm;
                if (raw_val == 0) {
                    target_pwm = 1000; // idle / armed
                } else {
                    // 1–255 → 1200–2000 µs
                    target_pwm = 1200 + ((uint32_t)raw_val * 800) / 255;
                }
                if (target_pwm > 2000) target_pwm = 2000;

                set_motor_pwm_us(i, target_pwm);
            }

            // Reset byte counter for next frame
            byte_index = 0;
        }

        // PWM hardware holds the last value indefinitely.
        // No watchdog — if Pi stops sending, motors hold their last speed.
        // The Pi-side arming/disarm logic controls whether value is 0 or live.
    }
}
