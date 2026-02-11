#include "pico/stdlib.h"
#include "hardware/pwm.h"
#include "hardware/spi.h"

// === CONFIGURATION ===
// For single-motor test, keep NUM_MOTORS = 1 and only wire GPIO 14.
// For full Pico, set NUM_MOTORS = 9 and update motor_pins accordingly.
#define NUM_MOTORS 1
#define SPI_BAUDRATE 1000000

// Motor configuration: {GPIO pin, min_us, max_us}
const uint motor_pins[NUM_MOTORS] = {14};
const uint16_t motor_min_us[NUM_MOTORS] = {1200};
const uint16_t motor_max_us[NUM_MOTORS] = {2700};

// PWM variables
uint pwm_slices[NUM_MOTORS];
uint pwm_channels[NUM_MOTORS];
uint16_t pwm_wrap;
// =====================

// SPI configuration
#define SPI_INST spi0
#define PIN_MISO 16
#define PIN_CS   17
#define PIN_SCK  18
#define PIN_MOSI 19

// Sync trigger from Pi (GPIO input on Pico)
#define PIN_SYNC 20

// Packet format: [0xAA, PWM1_H, PWM1_L, ..., PWMn_H, PWMn_L, 0x55]
#define PACKET_START 0xAA
#define PACKET_END 0x55
#define PACKET_BYTES (1 + (NUM_MOTORS * 2) + 1)

// Set PWM for specific motor based on microsecond pulse width
void set_motor_pwm_us(uint motor, uint16_t pulse_us) {
    if (motor >= NUM_MOTORS) return;

    // Clamp pulse width to valid range
    if (pulse_us < motor_min_us[motor]) pulse_us = motor_min_us[motor];
    if (pulse_us > motor_max_us[motor]) pulse_us = motor_max_us[motor];
    
    // Calculate PWM level (period is ~16ms = 16000µs)
    uint16_t level = (uint16_t)((pulse_us / 16000.0f) * (pwm_wrap + 1));
    if (level > pwm_wrap) level = pwm_wrap;
    
    // Set PWM
    pwm_set_chan_level(pwm_slices[motor], pwm_channels[motor], level);
}

// Initialize all PWMs
void init_all_pwms() {
    // Configure all motors
    for (int i = 0; i < NUM_MOTORS; i++) {
        gpio_set_function(motor_pins[i], GPIO_FUNC_PWM);
        pwm_slices[i] = pwm_gpio_to_slice_num(motor_pins[i]);
        pwm_channels[i] = pwm_gpio_to_channel(motor_pins[i]);
        
        // Configure PWM slice (only once per slice)
        if (i == 0 || pwm_slices[i] != pwm_slices[i-1]) {
            pwm_set_clkdiv(pwm_slices[i], 64.0f);
            pwm_set_wrap(pwm_slices[i], 31250);
            pwm_set_enabled(pwm_slices[i], true);
        }
        
        // Start with minimum
        set_motor_pwm_us(i, motor_min_us[i]);
    }
    
    pwm_wrap = 31250;  // Common wrap value
}

// Main function
volatile bool sync_triggered = false;
volatile bool pending_valid = false;
uint16_t pending_pwm[NUM_MOTORS];

void on_sync_edge(uint gpio, uint32_t events) {
    if (gpio == PIN_SYNC && (events & GPIO_IRQ_EDGE_RISE)) {
        sync_triggered = true;
    }
}

int main() {
    // Initialize all PWMs
    init_all_pwms();
    
    // Initialize SPI as slave
    spi_init(SPI_INST, SPI_BAUDRATE);
    spi_set_slave(SPI_INST, true);
    spi_set_format(SPI_INST, 8, SPI_CPOL_0, SPI_CPHA_0, SPI_MSB_FIRST);
    
    // Set SPI pins
    gpio_set_function(PIN_MISO, GPIO_FUNC_SPI);
    gpio_set_function(PIN_CS, GPIO_FUNC_SPI);
    gpio_set_function(PIN_SCK, GPIO_FUNC_SPI);
    gpio_set_function(PIN_MOSI, GPIO_FUNC_SPI);

    // Setup sync pin (input with pull-down) and IRQ
    gpio_init(PIN_SYNC);
    gpio_set_dir(PIN_SYNC, GPIO_IN);
    gpio_pull_down(PIN_SYNC);
    gpio_set_irq_enabled_with_callback(PIN_SYNC, GPIO_IRQ_EDGE_RISE, true, &on_sync_edge);
    
    // Main loop
    uint8_t packet[PACKET_BYTES];

    while (true) {
        // Read a full packet from SPI (blocking)
        spi_read_blocking(SPI_INST, 0, packet, PACKET_BYTES);

        // Validate packet framing
        if (packet[0] == PACKET_START && packet[PACKET_BYTES - 1] == PACKET_END) {
            for (int i = 0; i < NUM_MOTORS; i++) {
                int idx = 1 + (i * 2);
                uint16_t pwm_us = (uint16_t)((packet[idx] << 8) | packet[idx + 1]);
                pending_pwm[i] = pwm_us;
            }
            pending_valid = true;
        }

        // Apply update only on sync trigger
        if (sync_triggered && pending_valid) {
            sync_triggered = false;
            for (int i = 0; i < NUM_MOTORS; i++) {
                set_motor_pwm_us(i, pending_pwm[i]);
            }
            pending_valid = false;
        }
    }
}