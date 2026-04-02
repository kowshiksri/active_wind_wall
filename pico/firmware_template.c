#include "pico/stdlib.h"
#include "hardware/pwm.h"
#include "hardware/spi.h"
#include "hardware/gpio.h"
#include <stdbool.h>
#include <string.h>   // memset

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
// Each SPI frame contains 72 bytes: 2 bytes per motor (12-bit word, big-endian)
//   Byte layout per motor: [MSB (bits 11-8), LSB (bits 7-0)]
//   Word 0x0000       = armed/stopped  → 1000 µs
//   Word 0x0001-0x0FFF = running range → 1200-2000 µs
#define TOTAL_MOTORS    36
#define FRAME_BYTES     (TOTAL_MOTORS * 2)   // 72 bytes

// Calculate which bytes in the frame belong to this Pico.
// Each motor occupies 2 bytes, so byte range = motor range × 2.
// Example: PICO_ID=1 -> motors 9-17 -> bytes 18-35
#define MY_START      (PICO_ID * MOTORS_PER_PICO)
#define MY_END        (MY_START + MOTORS_PER_PICO)
#define MY_BYTE_START (MY_START * 2)
#define MY_BYTE_END   (MY_END   * 2)

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
volatile uint8_t  rx_frame[FRAME_BYTES];                 // Raw incoming SPI bytes (72 total)
volatile uint16_t active_frame_buffer[MOTORS_PER_PICO];  // Latched 12-bit words for current frame

// Synchronization state
volatile bool sync_pulse_detected = false;  // Set by IRQ when SYNC pin goes high
volatile uint32_t sync_counter = 0;         // Counts SYNC pulses for LED blink

// SPI frame tracking
volatile uint8_t byte_index = 0;  // Current position in 72-byte frame (0..71)

// ==========================================
// PWM CONTROL
// ==========================================
void set_motor_pwm_us(uint motor_index, uint16_t pulse_us) {
    // 0 = PWM off (no pulse output at all)
    if (pulse_us == 0) {
        pwm_set_chan_level(slices[motor_index], channels[motor_index], 0);
        return;
    }

    // Clamp to valid PWM range
    if (pulse_us < 1000) pulse_us = 1000;
    if (pulse_us > 2000) pulse_us = 2000;

    // Convert microseconds to PWM counter level.
    // clkdiv=80 → PWM clock = 125 MHz / 80 = 1.5625 MHz → 1.5625 counts/µs
    // wrap=31250 → period = 31250 / 1,562,500 Hz = 20 ms = 50 Hz ✓
    uint16_t level = (uint16_t)(pulse_us * 1.5625f);
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
 * Signals that a complete 72-byte frame has been transmitted
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

        // clkdiv=80 → 125 MHz / 80 = 1.5625 MHz PWM clock
        // wrap=31250 → 1,562,500 / 31250 = 50 Hz (20 ms period) ✓
        pwm_set_clkdiv(slices[i], 80.0f);
        pwm_set_wrap(slices[i], 31250);
        pwm_set_enabled(slices[i], true);

        // Initialize motor buffers to zero
        motor_values[i]      = 0;
        active_frame_buffer[i] = 0;
        
        // Boot with PWM off — no pulse until GUI arms the system
        set_motor_pwm_us(i, 0);
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
        // Read bytes as they arrive. Frame is 72 bytes: 2 bytes per motor (big-endian).
        // All bytes are stored in rx_frame[]; reconstruction happens on SYNC.
        while (spi_is_readable(SPI_INST)) {
            uint8_t rx = (uint8_t)spi_get_hw(SPI_INST)->dr;
            if (byte_index < FRAME_BYTES) {
                rx_frame[byte_index] = rx;
                byte_index++;
            }
            // Extra bytes beyond 72 are ignored until next SYNC
        }

        // === Step B: Process SYNC pulse ===
        // On SYNC rising edge: latch motor values and update PWM atomically
        if (sync_pulse_detected) {
            sync_pulse_detected = false;
            last_sync_time = get_absolute_time();

            // Reconstruct 12-bit words for this Pico's motors and latch atomically.
            // Each motor occupies 2 bytes in rx_frame at offset MY_BYTE_START + i*2.
            for (uint i = 0; i < MOTORS_PER_PICO; i++) {
                uint8_t msb = rx_frame[MY_BYTE_START + i * 2];
                uint8_t lsb = rx_frame[MY_BYTE_START + i * 2 + 1];
                active_frame_buffer[i] = ((uint16_t)msb << 8) | lsb;
            }

            // Convert 12-bit words (0–4095) to PWM pulse widths and update hardware.
            for (uint i = 0; i < MOTORS_PER_PICO; i++) {
                uint16_t word = active_frame_buffer[i];

                uint16_t target_pwm;
                if (word == 0) {
                    // 0x0000 = armed/stopped
                    target_pwm = 1000;
                } else {
                    // Map 0x0001–0x0FFF (1–4095) → 1200–2000 µs
                    // Resolution: 800 µs / 4094 steps ≈ 0.195 µs/step
                    target_pwm = 1200 + ((uint32_t)(word - 1) * 800) / 4094;
                }

                // Safety clamp
                if (target_pwm > 2000) target_pwm = 2000;

                set_motor_pwm_us(i, target_pwm);
            }

            // Reset frame for next cycle.
            // Clear the buffer so any truncated/short frame results in 0x0000
            // (armed/stopped) for missing motors rather than stale values.
            byte_index = 0;
            memset((void*)rx_frame, 0, FRAME_BYTES);
        }

        // === Step C: Safety watchdog ===
        // If no SYNC received for >200ms, assume communication lost
        // Set all motors to idle and blink LED rapidly
        if (absolute_time_diff_us(last_sync_time, get_absolute_time()) > SAFETY_TIMEOUT_US) {
            // Emergency stop: cut PWM output entirely (no pulse)
            for (uint i = 0; i < MOTORS_PER_PICO; i++) {
                set_motor_pwm_us(i, 0);
            }
            
            // Fast LED blink (5 Hz) to indicate error state
            gpio_put(LED_PIN, (to_ms_since_boot(get_absolute_time()) % 200) < 100);
        }
    }
}
