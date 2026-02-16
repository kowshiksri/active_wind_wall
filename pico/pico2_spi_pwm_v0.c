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
// Assumes contiguous pins for simplicity, adjust array if needed
#define MOTORS_PER_PICO 9
// Example: Pico 0 uses GP0-GP8. Pico 1 might use GP0-GP8 too if they are separate boards.
static const uint MOTOR_PINS[MOTORS_PER_PICO] = {0, 1, 2, 3, 4, 5, 6, 7, 8};
#define LED_PIN 25

// PWM settings
#define PWM_DIVIDER 64.0f
#define PWM_WRAP    31250

// SPI configuration
#define SPI_INST spi0
#define PIN_MISO 16 
#define PIN_CS   17 
#define PIN_SCK  18 
#define PIN_MOSI 19 

// Packet Protocol
#define PACKET_START 0xAA
#define PACKET_END   0x55
#define TOTAL_MOTORS 36
#define BYTES_PER_MOTOR 2

// Byte Math for "Sniffer"
// Frame = [START, M0H, M0L, ... M35H, M35L, END]
// OFFSET = Index where THIS Pico's data starts
#define OFFSET (1 + (PICO_ID * MOTORS_PER_PICO * BYTES_PER_MOTOR))

// Sync (latch) pin
#define SYNC_PIN 22

// Globals
uint slices[MOTORS_PER_PICO];
uint channels[MOTORS_PER_PICO];
volatile uint8_t next_frame_buffer[MOTORS_PER_PICO * BYTES_PER_MOTOR];
volatile bool sync_pulse_detected = false;
volatile uint32_t sync_counter = 0;

// ==========================================
// PWM CONTROL
// ==========================================
void set_motor_pwm_us(uint motor_index, uint16_t pulse_us) {
    // 1. Clamp to safe range (1000us to 2000us as requested)
    if (pulse_us < 1000) pulse_us = 1000;
    if (pulse_us > 2000) pulse_us = 2000;
    
    // 2. Convert to hardware cycles
    // Formula: level = pulse_us * (125MHz / 64 / 1000000) * 1000000 ? 
    // Simplified: pulse_us * 2.34375 for 60Hzish loop
    uint16_t level = (uint16_t)(pulse_us * 2.34375f);
    if (level > PWM_WRAP) level = PWM_WRAP;
    
    pwm_set_chan_level(slices[motor_index], channels[motor_index], level);
}

void apply_next_frame(void) {
    for (uint i = 0; i < MOTORS_PER_PICO; i++) {
        // Reconstruct 16-bit value from buffer (Big Endian)
        uint16_t high_byte = next_frame_buffer[i * 2];
        uint16_t low_byte  = next_frame_buffer[i * 2 + 1];
        uint16_t pwm_us    = (high_byte << 8) | low_byte;
        
        set_motor_pwm_us(i, pwm_us);
    }
}

// ==========================================
// INTERRUPT HANDLER
// ==========================================
void sync_irq_handler(uint gpio, uint32_t events) {
    if (gpio == SYNC_PIN) {
        // Trigger main loop to update PWM
        sync_pulse_detected = true;
        
        // VISIBLE HEARTBEAT:
        // Toggle LED every 20 frames (approx 20Hz blink at 400Hz refresh)
        // This confirms the SYNC line is actually firing
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
    stdio_init_all(); // Optional, for debug prints if USB connected

    // 1. Initialize LED
    gpio_init(LED_PIN);
    gpio_set_dir(LED_PIN, GPIO_OUT);
    gpio_put(LED_PIN, 1); // Solid ON means "Booted, waiting for Sync"

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
    }

    // 3. Initialize SPI (Slave)
    spi_init(SPI_INST, 1000000);
    spi_set_slave(SPI_INST, true);
    gpio_set_function(PIN_MISO, GPIO_FUNC_SPI);
    gpio_set_function(PIN_CS, GPIO_FUNC_SPI);
    gpio_set_function(PIN_SCK, GPIO_FUNC_SPI);
    gpio_set_function(PIN_MOSI, GPIO_FUNC_SPI);

    // 4. Initialize Sync Pin
    gpio_init(SYNC_PIN);
    gpio_set_dir(SYNC_PIN, GPIO_IN);
    // Use Pull Down so floating pin doesn't trigger random syncs
    gpio_pull_down(SYNC_PIN); 
    gpio_set_irq_enabled_with_callback(SYNC_PIN, GPIO_IRQ_EDGE_RISE, true, &sync_irq_handler);

    // Variables for SPI State Machine
    int frame_index = 0;
    bool header_found = false;
    uint8_t buffer_limit = MOTORS_PER_PICO * BYTES_PER_MOTOR;

    while (true) {
        // --- A. SPI SNIFFER ---
        if (spi_is_readable(SPI_INST)) {
            uint8_t rx;
            spi_read_blocking(SPI_INST, 0, &rx, 1);

            if (!header_found) {
                if (rx == PACKET_START) {
                    header_found = true;
                    frame_index = 1; // Header is byte 0
                }
            } else {
                // We are inside a frame. Check if this byte belongs to US.
                // Current 'frame_index' represents the position in the GLOBAL packet.
                
                // If index is within OUR range: [OFFSET ... OFFSET+17]
                if (frame_index >= OFFSET && frame_index < (OFFSET + buffer_limit)) {
                    // Map global index to local buffer index (0..17)
                    next_frame_buffer[frame_index - OFFSET] = rx;
                }

                // Advance Counter
                frame_index++;

                // Reset on End Byte or Overflow
                // (74 bytes is standard frame size: 1+72+1)
                if (rx == PACKET_END || frame_index > 100) {
                    header_found = false;
                    frame_index = 0;
                }
            }
        }

        // --- B. UPDATE MOTORS (ON SYNC) ---
        if (sync_pulse_detected) {
            sync_pulse_detected = false;
            apply_next_frame();
        }
    }
}