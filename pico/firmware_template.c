#include "pico/stdlib.h"
#include "hardware/pwm.h"
#include "hardware/spi.h"
#include "hardware/gpio.h"
#include <stdbool.h>

// ==========================================
// CONFIGURATION
// ==========================================

// Board identifier - IMPORTANT: Change this for each Pico board (0, 1, 2, or 3)
// Each board controls 9 motors based on its ID
#define PICO_ID {{PICO_ID}}

// Motor configuration
#define MOTORS_PER_PICO 9
static const uint MOTOR_PINS[MOTORS_PER_PICO] = {0, 1, 2, 3, 4, 5, 6, 7, 8};

// Status LED
#define LED_PIN 25

// SPI Configuration (Slave mode)
// Receives motor commands from Raspberry Pi via SPI
#define SPI_INST spi0
#define PIN_MISO 19   // SPI0 TX (to Pi MISO) - Currently unused
#define PIN_CS   17   // SPI0 CSn (from Pi CE0)
#define PIN_SCK  18   // SPI0 SCK (clock)
#define PIN_MOSI 16   // SPI0 RX (from Pi MOSI) - Data input

// Frame structure
// Total system: 36 motors across 4 Pico boards (9 motors each)
// Each SPI frame contains 36 bytes, one per motor
#define TOTAL_MOTORS    36
#define FRAME_BYTES     TOTAL_MOTORS

// Calculate which bytes in the frame belong to this Pico
// Example: PICO_ID=1 -> motors 9-17 (bytes 9-17 in frame)
#define MY_START (PICO_ID * MOTORS_PER_PICO)
#define MY_END   (MY_START + MOTORS_PER_PICO)

// Synchronization pulse input
// Rising edge triggers frame latch and PWM update
#define SYNC_PIN 22

// ==========================================
// GLOBAL STATE
// ==========================================

// PWM hardware configuration for each motor
uint slices[MOTORS_PER_PICO];      // PWM slice numbers
uint channels[MOTORS_PER_PICO];    // PWM channel numbers (A or B)

// Motor control buffers
volatile uint8_t motor_values[MOTORS_PER_PICO];         // Incoming values from SPI (0-255)
volatile uint8_t active_frame_buffer[MOTORS_PER_PICO];  // Latched values for current frame

// Synchronization state
volatile bool sync_pulse_detected = false;  // Set by IRQ when SYNC pin goes high
volatile uint32_t sync_counter = 0;         // Counts SYNC pulses for LED blink

// SPI frame tracking
volatile uint8_t byte_index = 0;  // Current position in 36-byte frame (0..35)

// ==========================================
// PWM CONTROL
// ==========================================
void set_motor_pwm_us(uint motor_index, uint16_t pulse_us) {
    // Clamp to valid PWM range
    if (pulse_us < 1000) pulse_us = 1000;
    if (pulse_us > 2000) pulse_us = 2000;

    // Convert microseconds to PWM counter level
    uint16_t level = (uint16_t)(pulse_us * 2.34375f);
    if (level > 31250) level = 31250;

    // Update PWM hardware
    pwm_set_chan_level(slices[motor_index], channels[motor_index], level);
}

// ==========================================
// SYNC INTERRUPT HANDLER
// ==========================================

/**
 * SYNC pin interrupt handler
 * 
 * Called on rising edge of SYNC signal from Raspberry Pi.
 * Signals that a complete 36-byte frame has been transmitted
 * and PWM values should be updated atomically.
 * 
 * Also blinks LED every 20 SYNC pulses to indicate activity.
 */
void sync_irq_handler(uint gpio, uint32_t events) {
    if (gpio == SYNC_PIN) {
        sync_pulse_detected = true;
        sync_counter++;
        
        // Toggle LED every 20 frames for visual feedback
        if (sync_counter >= 20) {
            gpio_xor_mask(1u << LED_PIN);
            sync_counter = 0;
        }
    }
}

// ==========================================
// MAIN PROGRAM
// ==========================================
int main() {
    stdio_init_all();

    // Initialize status LED (on at startup)
    gpio_init(LED_PIN);
    gpio_set_dir(LED_PIN, GPIO_OUT);
    gpio_put(LED_PIN, 1);

    // Initialize PWM for all motors
    for (uint i = 0; i < MOTORS_PER_PICO; i++) {
        // Configure GPIO for PWM output
        gpio_set_function(MOTOR_PINS[i], GPIO_FUNC_PWM);
        slices[i] = pwm_gpio_to_slice_num(MOTOR_PINS[i]);
        channels[i] = pwm_gpio_to_channel(MOTOR_PINS[i]);

        pwm_set_clkdiv(slices[i], 64.0f);
        pwm_set_wrap(slices[i], 31250);
        pwm_set_enabled(slices[i], true);

        // Initialize motor buffers to zero
        motor_values[i] = 0;
        active_frame_buffer[i] = 0;
        
        // Set motors to idle position (1000 us pulse)
        set_motor_pwm_us(i, 1000);
    }

    // Configure SPI in slave mode
    // Baud rate parameter is ignored in slave mode (clock provided by master)
    spi_init(SPI_INST, 1000000);
    spi_set_slave(SPI_INST, true);
    
    // Configure SPI pins
    gpio_set_function(PIN_MISO, GPIO_FUNC_SPI);
    gpio_set_function(PIN_CS,   GPIO_FUNC_SPI);
    gpio_set_function(PIN_SCK,  GPIO_FUNC_SPI);
    gpio_set_function(PIN_MOSI, GPIO_FUNC_SPI);

    // Configure SYNC pin with interrupt on rising edge
    gpio_init(SYNC_PIN);
    gpio_set_dir(SYNC_PIN, GPIO_IN);
    gpio_pull_down(SYNC_PIN);
    gpio_set_irq_enabled_with_callback(SYNC_PIN, GPIO_IRQ_EDGE_RISE, true, &sync_irq_handler);

    // Safety watchdog timing
    absolute_time_t last_sync_time = get_absolute_time();
    const uint64_t SAFETY_TIMEOUT_US = 200000; // 200 ms without SYNC = communication loss

    // ==========================================
    // MAIN LOOP
    // ==========================================
    while (true) {
        
        // === Step A: Receive SPI data ===
        // Read bytes as they arrive over SPI
        // Each byte represents one motor value (0-255) in the 36-motor array
        while (spi_is_readable(SPI_INST)) {
            uint8_t rx = (uint8_t)spi_get_hw(SPI_INST)->dr;

            uint8_t idx = byte_index;
            if (byte_index < FRAME_BYTES) {
                byte_index++;
            } else {
                // Extra bytes beyond 36 are ignored until next SYNC
            }

            // Store only bytes that belong to this Pico's motors
            if (idx >= MY_START && idx < MY_END) {
                motor_values[idx - MY_START] = rx;
            }
        }

        // === Step B: Process SYNC pulse ===
        // On SYNC rising edge: latch motor values and update PWM atomically
        if (sync_pulse_detected) {
            sync_pulse_detected = false;
            last_sync_time = get_absolute_time();

            // Atomic snapshot: copy latest SPI values to active buffer
            for (uint i = 0; i < MOTORS_PER_PICO; i++) {
                active_frame_buffer[i] = motor_values[i];
            }

            // Convert motor values (0-255) to PWM pulse widths and update hardware
            for (uint i = 0; i < MOTORS_PER_PICO; i++) {
                uint8_t raw_val = active_frame_buffer[i];

                uint16_t target_pwm;
                if (raw_val == 0) {
                    // 0 = explicit idle/stop command
                    target_pwm = 1000;
                } else {
                    // Map 1-255 to 1200-2000 us (linear scaling)
                    // 1200 us = minimum active, 2000 us = maximum
                    target_pwm = 1200 + ((uint32_t)raw_val * 800) / 255;
                }
                
                // Safety clamp
                if (target_pwm > 2000) target_pwm = 2000;
                
                set_motor_pwm_us(i, target_pwm);
            }

            // Reset frame byte counter for next transmission cycle
            byte_index = 0;
        }

        // === Step C: Safety watchdog ===
        // If no SYNC received for >200ms, assume communication lost
        // Set all motors to idle and blink LED rapidly
        if (absolute_time_diff_us(last_sync_time, get_absolute_time()) > SAFETY_TIMEOUT_US) {
            // Emergency stop: all motors to idle
            for (uint i = 0; i < MOTORS_PER_PICO; i++) {
                set_motor_pwm_us(i, 1000);
            }
            
            // Fast LED blink (5 Hz) to indicate error state
            gpio_put(LED_PIN, (to_ms_since_boot(get_absolute_time()) % 200) < 100);
        }
    }
}
