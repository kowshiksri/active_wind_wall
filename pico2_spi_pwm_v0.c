#include "pico/stdlib.h"
#include "hardware/pwm.h"
#include "hardware/spi.h"

// === CONFIGURATION ===
#define NUM_MOTORS 2  // Change to 9 later
#define SPI_BAUDRATE 1000000

// Motor configuration: {GPIO pin, min_us, max_us}
const uint motor_pins[NUM_MOTORS] = {14, 15};
const uint16_t motor_min_us[NUM_MOTORS] = {1200, 1200};
const uint16_t motor_max_us[NUM_MOTORS] = {2700, 2700};

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

// Set PWM for specific motor based on intensity (0-100)
void set_motor_pwm(uint motor, uint8_t intensity) {
    if (motor >= NUM_MOTORS) return;
    
    // Calculate pulse width (min_us - max_us)
    uint16_t pulse_us;
    if (intensity == 0) {
        pulse_us = motor_min_us[motor];
    } else if (intensity >= 100) {
        pulse_us = motor_max_us[motor];
    } else {
        // Linear mapping: intensity 0-100 -> min_us - max_us
        pulse_us = motor_min_us[motor] + 
                  ((uint32_t)intensity * (motor_max_us[motor] - motor_min_us[motor])) / 100;
    }
    
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
        set_motor_pwm(i, 0);
    }
    
    pwm_wrap = 31250;  // Common wrap value
}

// Main function
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
    
    // Main loop
    uint8_t motor_data[NUM_MOTORS];
    
    while (true) {
        // Read data for all motors from SPI
        for (int i = 0; i < NUM_MOTORS; i++) {
            spi_read_blocking(SPI_INST, 0, &motor_data[i], 1);
        }
        
        // Update all motors
        for (int i = 0; i < NUM_MOTORS; i++) {
            set_motor_pwm(i, motor_data[i]);
        }
    }
}