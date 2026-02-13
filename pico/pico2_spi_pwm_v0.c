#include <stdbool.h>
#include "pico/stdlib.h"
#include "hardware/pwm.h"
#include "hardware/spi.h"
#include "hardware/clocks.h" // Required for Pico 2 clock check

// === CONFIGURATION ===
#define NUM_MOTORS 1
#define SPI_BAUDRATE 1000000

// MOTOR PIN: GP0 (Physical Pin 1)
static const uint motor_pins[NUM_MOTORS] = {0}; 
static const uint16_t motor_min_us[NUM_MOTORS] = {1000};
static const uint16_t motor_max_us[NUM_MOTORS] = {2000};

// PWM bookkeeping
static uint pwm_slices[NUM_MOTORS];
static uint pwm_channels[NUM_MOTORS];

// === PROTOCOL: [0xA5, ADDR, LSB, MSB, 0x5A] ===
#define RECORD_START 0xA5
#define RECORD_END   0x5A

#define THIS_PICO_ID   0u
#define PICO_ID_BITS   2u
#define MOTOR_ID_BITS  4u
#define PICO_ID_MASK   ((1u << PICO_ID_BITS) - 1u)
#define MOTOR_ID_MASK  ((1u << MOTOR_ID_BITS) - 1u)

// SPI PINS
#define SPI_INST spi0
#define PIN_MISO 16
#define PIN_CS   17
#define PIN_SCK  18
#define PIN_MOSI 19 // RX

#define PIN_SYNC 20

// State Machine
typedef enum {
    STREAM_WAIT_START = 0,
    STREAM_WAIT_ADDRESS,
    STREAM_WAIT_PWM_LSB,
    STREAM_WAIT_PWM_MSB,
    STREAM_WAIT_END
} stream_state_t;

typedef struct {
    stream_state_t state;
    uint8_t address;
    uint16_t pwm_value;
} stream_parser_t;

static stream_parser_t parser = { .state = STREAM_WAIT_START, .address = 0, .pwm_value = 0 };

// Data Holding
static volatile bool sync_triggered = false;
static uint16_t pending_pwm_us[NUM_MOTORS];
static bool pending_fresh[NUM_MOTORS];

// --- HELPER FUNCTIONS ---

static inline uint16_t clamp_pwm(uint motor, uint16_t pulse_us) {
    if (motor >= NUM_MOTORS) return pulse_us;
    if (pulse_us < motor_min_us[motor]) return motor_min_us[motor];
    if (pulse_us > motor_max_us[motor]) return motor_max_us[motor];
    return pulse_us;
}

static void set_motor_pwm_us(uint motor, uint16_t pulse_us) {
    if (motor >= NUM_MOTORS) return;
    pulse_us = clamp_pwm(motor, pulse_us);

    // DIRECT WRITE: 1 tick = 1 us (Clock is tuned below)
    pwm_set_chan_level(pwm_slices[motor], pwm_channels[motor], pulse_us);
}

// === CRITICAL FIX FOR PICO 2 ===
static void init_all_pwms(void) {
    // 1. Get System Clock (150MHz on Pico 2)
    uint32_t sys_clk = clock_get_hz(clk_sys);

    // 2. Calculate Divider: 150MHz / 150.0 = 1MHz (1us per tick)
    float divider = (float)sys_clk / 1000000.0f;
    
    // 3. Period: 20ms = 20,000 ticks
    uint16_t pwm_wrap = 20000; 

    for (uint i = 0; i < NUM_MOTORS; i++) {
        gpio_set_function(motor_pins[i], GPIO_FUNC_PWM);
        pwm_slices[i] = pwm_gpio_to_slice_num(motor_pins[i]);
        pwm_channels[i] = pwm_gpio_to_channel(motor_pins[i]);

        if (i == 0 || pwm_slices[i] != pwm_slices[i - 1]) {
            pwm_set_clkdiv(pwm_slices[i], divider);
            pwm_set_wrap(pwm_slices[i], pwm_wrap);
            pwm_set_enabled(pwm_slices[i], true);
        }

        // Init to Min
        pending_pwm_us[i] = motor_min_us[i];
        pending_fresh[i] = false;
        set_motor_pwm_us(i, motor_min_us[i]);
    }
}

// --- SPI PARSER ---

static void handle_complete_record(uint8_t address, uint16_t pwm_value) {
    uint8_t pico_id = (address >> MOTOR_ID_BITS) & PICO_ID_MASK;
    uint8_t motor_id = address & MOTOR_ID_MASK;

    if (pico_id != THIS_PICO_ID || motor_id >= NUM_MOTORS) return;

    pending_pwm_us[motor_id] = clamp_pwm(motor_id, pwm_value);
    pending_fresh[motor_id] = true;
}

static void process_spi_byte(uint8_t byte) {
    switch (parser.state) {
        case STREAM_WAIT_START:
            if (byte == RECORD_START) parser.state = STREAM_WAIT_ADDRESS;
            break;
        case STREAM_WAIT_ADDRESS:
            if (byte == RECORD_START) parser.state = STREAM_WAIT_ADDRESS;
            else { parser.address = byte; parser.state = STREAM_WAIT_PWM_LSB; }
            break;
        case STREAM_WAIT_PWM_LSB:
            if (byte == RECORD_START) parser.state = STREAM_WAIT_ADDRESS;
            else { parser.pwm_value = byte; parser.state = STREAM_WAIT_PWM_MSB; }
            break;
        case STREAM_WAIT_PWM_MSB:
            if (byte == RECORD_START) parser.state = STREAM_WAIT_ADDRESS;
            else { parser.pwm_value |= ((uint16_t)byte << 8); parser.state = STREAM_WAIT_END; }
            break;
        case STREAM_WAIT_END:
            if (byte == RECORD_END) {
                handle_complete_record(parser.address, parser.pwm_value);
                parser.state = STREAM_WAIT_START;
            } else if (byte == RECORD_START) {
                parser.state = STREAM_WAIT_ADDRESS;
            } else {
                parser.state = STREAM_WAIT_START;
            }
            break;
    }
}

static void apply_pending_values(void) {
    for (uint i = 0; i < NUM_MOTORS; i++) {
        if (pending_fresh[i]) {
            set_motor_pwm_us(i, pending_pwm_us[i]);
            pending_fresh[i] = false;
        }
    }
}

static void on_sync_edge(uint gpio, uint32_t events) {
    if (gpio == PIN_SYNC) sync_triggered = true;
}

// --- MAIN ---
int main(void) {
    // 1. LED Setup
    const uint LED_PIN = 25;
    gpio_init(LED_PIN);
    gpio_set_dir(LED_PIN, GPIO_OUT);
    gpio_put(LED_PIN, 1);

    // 2. PWM Setup (Pico 2 Fix Applied)
    init_all_pwms();

    // 3. SPI Setup
    spi_init(SPI_INST, SPI_BAUDRATE);
    spi_set_slave(SPI_INST, true);
    gpio_set_function(PIN_MISO, GPIO_FUNC_SPI);
    gpio_set_function(PIN_CS,   GPIO_FUNC_SPI);
    gpio_set_function(PIN_SCK,  GPIO_FUNC_SPI);
    gpio_set_function(PIN_MOSI, GPIO_FUNC_SPI);

    // 4. Sync Setup
    gpio_init(PIN_SYNC);
    gpio_set_dir(PIN_SYNC, GPIO_IN);
    gpio_pull_down(PIN_SYNC);
    gpio_set_irq_enabled_with_callback(PIN_SYNC, GPIO_IRQ_EDGE_RISE, true, &on_sync_edge);

    uint64_t last_blink_us = time_us_64();

    while (true) {
        // Read SPI
        while (spi_is_readable(SPI_INST)) {
            uint8_t byte = 0;
            spi_read_blocking(SPI_INST, 0, &byte, 1);
            process_spi_byte(byte);
        }

        // Apply Updates
        if (sync_triggered) {
            sync_triggered = false;
            apply_pending_values();
        }

        // Heartbeat (Verify Code Running)
        uint64_t now = time_us_64();
        if (now - last_blink_us >= 250000) {
            gpio_xor_mask(1u << LED_PIN);
            last_blink_us = now;
        }
    }
}