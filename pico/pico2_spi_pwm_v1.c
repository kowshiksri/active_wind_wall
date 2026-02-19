#include "pico/stdlib.h"
#include "hardware/pwm.h"
#include "hardware/spi.h"
#include "hardware/gpio.h"
#include <stdbool.h>

// ==========================================
// CONFIGURATION
// ==========================================
#define PICO_ID 0          // 0,1,2,3 for your 4 boards

#define MOTORS_PER_PICO 9
static const uint MOTOR_PINS[MOTORS_PER_PICO] = {0,1,2,3,4,5,6,7,8};

#define LED_PIN 25

// PWM settings
#define PWM_DIVIDER 64.0f
#define PWM_WRAP    31250

// SPI: using SPI0 on Pico 2
#define SPI_INST spi0
#define PIN_MISO 19   // SPI0 TX (Pico MISO -> Pi MISO)
#define PIN_CS   17   // SPI0 CSn
#define PIN_SCK  18   // SPI0 SCK
#define PIN_MOSI 16   // SPI0 RX (Pico MOSI <- Pi MOSI)

// Frame
#define FRAME_BYTES 36
#define TOTAL_MOTORS 36

#define MY_START (PICO_ID * MOTORS_PER_PICO)
#define MY_END   (MY_START + MOTORS_PER_PICO)

// SYNC pin
#define SYNC_PIN 22

// Globals
uint slices[MOTORS_PER_PICO];
uint channels[MOTORS_PER_PICO];

static uint8_t frame_buffer[FRAME_BYTES];
static volatile bool start_new_frame = false;

volatile uint8_t active_frame_buffer[MOTORS_PER_PICO];

volatile uint32_t sync_counter = 0;

// ==========================================
// PWM CONTROL
// ==========================================
void set_motor_pwm_us(uint motor_index, uint16_t pulse_us) {
    if (pulse_us < 1000) pulse_us = 1000;
    if (pulse_us > 2000) pulse_us = 2000;

    uint16_t level = (uint16_t)(pulse_us * 2.34375f);
    if (level > PWM_WRAP) level = PWM_WRAP;

    pwm_set_chan_level(slices[motor_index], channels[motor_index], level);
}

// ==========================================
// SYNC IRQ
// ==========================================
void sync_irq_handler(uint gpio, uint32_t events) {
    if (gpio == SYNC_PIN) {
        start_new_frame = true;

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

    // PWM
    for (uint i = 0; i < MOTORS_PER_PICO; i++) {
        gpio_set_function(MOTOR_PINS[i], GPIO_FUNC_PWM);
        slices[i] = pwm_gpio_to_slice_num(MOTOR_PINS[i]);
        channels[i] = pwm_gpio_to_channel(MOTOR_PINS[i]);

        pwm_set_clkdiv(slices[i], 64.0f);
        pwm_set_wrap(slices[i], 31250);
        pwm_set_enabled(slices[i], true);

        set_motor_pwm_us(i, 1000);
        active_frame_buffer[i] = 0;
    }

    // SPI slave init
    spi_init(SPI_INST, 1000000);     // baud ignored in slave mode
    spi_set_slave(SPI_INST, true);
    gpio_set_function(PIN_MISO, GPIO_FUNC_SPI);
    gpio_set_function(PIN_CS,   GPIO_FUNC_SPI);
    gpio_set_function(PIN_SCK,  GPIO_FUNC_SPI);
    gpio_set_function(PIN_MOSI, GPIO_FUNC_SPI);

    // SYNC
    gpio_init(SYNC_PIN);
    gpio_set_dir(SYNC_PIN, GPIO_IN);
    gpio_pull_down(SYNC_PIN);
    gpio_set_irq_enabled_with_callback(SYNC_PIN, GPIO_IRQ_EDGE_RISE, true, &sync_irq_handler);

    absolute_time_t last_sync_time = get_absolute_time();
    const uint64_t SAFETY_TIMEOUT_US = 200000; // 200ms

    while (true) {
        // A. When SYNC triggers, read exactly 36 bytes blocking
        if (start_new_frame) {
            start_new_frame = false;
            last_sync_time = get_absolute_time();

            // 1) Blocking read of 36 bytes
            for (int i = 0; i < FRAME_BYTES; i++) {
                // Wait until a byte is available
                while (!spi_is_readable(SPI_INST)) {
                    tight_loop_contents();
                }
                frame_buffer[i] = (uint8_t)spi_get_hw(SPI_INST)->dr;
            }

            // 2) Copy this Pico's bytes into active_frame_buffer
            for (uint i = 0; i < MOTORS_PER_PICO; i++) {
                uint idx = MY_START + i;  // 0..35
                active_frame_buffer[i] = frame_buffer[idx];
            }

            // 3) Pre-load these 9 bytes into TX FIFO for Pi readback
            for (uint i = 0; i < MOTORS_PER_PICO; i++) {
                while (!spi_is_writable(SPI_INST)) {
                    tight_loop_contents();
                }
                spi_get_hw(SPI_INST)->dr = active_frame_buffer[i];
            }

            // 4) Apply PWM
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

        // B. Safety: if no sync for too long, go to idle PWM
        if (absolute_time_diff_us(last_sync_time, get_absolute_time()) > SAFETY_TIMEOUT_US) {
            for (uint i = 0; i < MOTORS_PER_PICO; i++) {
                set_motor_pwm_us(i, 1000);
            }
            gpio_put(LED_PIN, (to_ms_since_boot(get_absolute_time()) % 200) < 100);
        }
    }
}
