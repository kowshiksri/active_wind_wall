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
#define PIN_MISO 19 
#define PIN_CS   17 
#define PIN_SCK  18 
#define PIN_MOSI 16 

// Packet Protocol
#define PACKET_START 0xAA
#define PACKET_END   0x55
#define TOTAL_MOTORS 36
#define BYTES_PER_MOTOR 1

// Byte Math for "Sniffer"
// Frame = [START, M0H, M0L, ... M35H, M35L, END]
// OFFSET = Index where THIS Pico's data starts
#define OFFSET ((PICO_ID * MOTORS_PER_PICO * BYTES_PER_MOTOR))

// Sync (latch) pin
#define SYNC_PIN 22

// Globals
uint slices[MOTORS_PER_PICO];
uint channels[MOTORS_PER_PICO];
volatile uint8_t next_frame_buffer[MOTORS_PER_PICO * BYTES_PER_MOTOR];
volatile uint8_t active_frame_buffer[MOTORS_PER_PICO];
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

// void apply_next_frame(void) {
//     for (uint i = 0; i < MOTORS_PER_PICO; i++) {
//         uint8_t raw_val = next_frame_buffer[i];
        
//         uint16_t target_pwm;

//         // FIX: If value is 0, go to SAFE IDLE (1000)
//         // This prevents "Disconnect = 1200"
//         if (raw_val == 0) {
//             target_pwm = 1000;
//         } 
//         else {
//             // Map 1-255 -> 1200-2000
//             // Formula: 1200 + (raw_val * 800) / 255
//             target_pwm = 1200 + ((uint32_t)raw_val * 800) / 255;
//         }

//         if (target_pwm > 2000) target_pwm = 2000;
//         set_motor_pwm_us(i, target_pwm);
//     }
// }

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
    
    // After the Sync Pin init (step 4), before the while loop:
    for (uint i = 0; i < MOTORS_PER_PICO; i++) {
        next_frame_buffer[i] = 0;
        active_frame_buffer[i] = 0;
    }

    // New simpler variables — remove old ones (frame_index, header_found, buffer_limit)
    int byte_count = 0;
    absolute_time_t last_sync_time    = get_absolute_time();
    absolute_time_t last_spi_byte_time = get_absolute_time();
    const uint64_t SAFETY_TIMEOUT_US  = 200000;
    const uint64_t FRAME_TIMEOUT_US   = 5000;

    // MY_START and MY_END: which byte positions in the 36-byte frame belong to this Pico
    const int MY_START = PICO_ID * MOTORS_PER_PICO;          // Pico 0 = 0
    const int MY_END   = MY_START + MOTORS_PER_PICO;          // Pico 0 = 9

    while (true) {

        // --- A. SPI RECEIVE: Drain FIFO natively without touching TX ---
        // Read ALL available bytes in one shot to prevent FIFO overflow
        while (spi_is_readable(SPI_INST)) {
            // Directly pop the hardware data register. This avoids spi_read_blocking
            // trying to push dummy bytes into the TX FIFO and deadlocking the slave.
            uint8_t rx = (uint8_t)spi_get_hw(SPI_INST)->dr;
            last_spi_byte_time = get_absolute_time();

            // Only store bytes that belong to this Pico
            if (byte_count >= MY_START && byte_count < MY_END) {
                next_frame_buffer[byte_count - MY_START] = rx;
            }

            byte_count++;

            // After 36 bytes, reset for next frame
            if (byte_count >= TOTAL_MOTORS) {
                byte_count = 0;
                break; // Exit after completing one frame
            }
        }

        // Frame stall: if mid-frame and no byte for 5ms, realign
        if (byte_count > 0 &&
            absolute_time_diff_us(last_spi_byte_time, get_absolute_time()) > FRAME_TIMEOUT_US) {
            byte_count = 0;
        }

        // --- B. APPLY ON SYNC ---
        if (sync_pulse_detected) {
            sync_pulse_detected = false;
            last_sync_time = get_absolute_time();
            
            // CRITICAL: Hard realign the frame tracker. This guarantees that even 
            // if a byte was corrupted or dropped, the next frame starts at 0.
            byte_count = 0;
            
            // ATOMIC COPY: Snapshot the incoming buffer
            for (uint i = 0; i < MOTORS_PER_PICO; i++) {
                active_frame_buffer[i] = next_frame_buffer[i];
            }
            
            // Now apply from the stable snapshot
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
            
            // LED heartbeat
            sync_counter++;
            if (sync_counter >= 20) {
                gpio_xor_mask(1u << LED_PIN);
                sync_counter = 0;
            }
        }

        // --- C. SAFETY WATCHDOG ---
        if (absolute_time_diff_us(last_sync_time, get_absolute_time()) > SAFETY_TIMEOUT_US) {
            for (uint i = 0; i < MOTORS_PER_PICO; i++) {
                set_motor_pwm_us(i, 1000);
            }
            gpio_put(LED_PIN, (to_ms_since_boot(get_absolute_time()) % 200) < 100);
        }
    }
}