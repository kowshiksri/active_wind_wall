#include "pico/stdlib.h"
#include "hardware/pwm.h"
#include "hardware/spi.h"

// === STEP 3: ADDRESSED STREAM PARSER ===
#define NUM_MOTORS 9
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

// Packet format: [START, ADDRESS, INTENSITY, END]
#define PACKET_START 0xAA
#define PACKET_END   0x55

// THIS PICO'S ADDRESS RANGE
// Pico 0: addresses 0-8
// Pico 1: addresses 9-17
// Pico 2: addresses 18-26
// Pico 3: addresses 27-35
#define MY_BASE_ADDRESS 0  // CHANGE THIS FOR EACH PICO (0, 9, 18, 27)

// Motor pins (GP14-GP22 for 9 motors)
const uint motor_pins[NUM_MOTORS] = {14, 15, 16, 17, 18, 19, 20, 21, 22};
uint motor_slices[NUM_MOTORS];
uint motor_channels[NUM_MOTORS];

// Motor range
#define MIN_PULSE_US 1200
#define MAX_PULSE_US 2700

// Set motor from intensity (0-100)
void set_motor_intensity(uint8_t motor_idx, uint8_t intensity) {
    if (motor_idx >= NUM_MOTORS) return;
    if (intensity > 100) intensity = 100;
    
    // Map 0-100 to 1200-2700 µs
    uint16_t pulse_us = MIN_PULSE_US + ((uint32_t)intensity * (MAX_PULSE_US - MIN_PULSE_US)) / 100;
    
    // Convert to PWM level: pulse_us * 2.34375
    uint16_t level = (uint16_t)(pulse_us * 2.34375f);
    if (level > PWM_WRAP) level = PWM_WRAP;
    
    pwm_set_chan_level(motor_slices[motor_idx], motor_channels[motor_idx], level);
}

void init_all_motors() {
    for (int i = 0; i < NUM_MOTORS; i++) {
        gpio_set_function(motor_pins[i], GPIO_FUNC_PWM);
        motor_slices[i] = pwm_gpio_to_slice_num(motor_pins[i]);
        motor_channels[i] = pwm_gpio_to_channel(motor_pins[i]);
        
        // Configure PWM slice (only once per unique slice)
        if (i == 0 || motor_slices[i] != motor_slices[i-1]) {
            pwm_set_clkdiv(motor_slices[i], PWM_DIVIDER);
            pwm_set_wrap(motor_slices[i], PWM_WRAP);
            pwm_set_enabled(motor_slices[i], true);
        }
        
        // Start at minimum
        set_motor_intensity(i, 0);
    }
}

int main() {
    // Initialize LED
    gpio_init(LED_PIN);
    gpio_set_dir(LED_PIN, GPIO_OUT);
    gpio_put(LED_PIN, 0);

    // Initialize all motors
    init_all_motors();

    // Initialize SPI slave
    spi_init(SPI_INST, 1000000);
    spi_set_slave(SPI_INST, true);
    gpio_set_function(PIN_MISO, GPIO_FUNC_SPI);
    gpio_set_function(PIN_CS, GPIO_FUNC_SPI);
    gpio_set_function(PIN_SCK, GPIO_FUNC_SPI);
    gpio_set_function(PIN_MOSI, GPIO_FUNC_SPI);

    // Stream parser state
    uint8_t byte;
    uint8_t address;
    uint8_t intensity;
    uint8_t end_byte;
    uint32_t packets_received = 0;
    uint32_t last_blink = 0;
    bool led_state = false;

    while (true) {
        // Read bytes continuously
        spi_read_blocking(SPI_INST, 0, &byte, 1);
        
        // Look for START byte
        if (byte == PACKET_START) {
            // Read next 3 bytes: address, intensity, end
            spi_read_blocking(SPI_INST, 0, &address, 1);
            spi_read_blocking(SPI_INST, 0, &intensity, 1);
            spi_read_blocking(SPI_INST, 0, &end_byte, 1);
            
            // Validate packet and check if it's for us
            if (end_byte == PACKET_END && address >= MY_BASE_ADDRESS && address < (MY_BASE_ADDRESS + NUM_MOTORS)) {
                // This packet is for us!
                uint8_t motor_idx = address - MY_BASE_ADDRESS;
                set_motor_intensity(motor_idx, intensity);
                packets_received++;
                
                // Flash LED on each valid packet
                gpio_put(LED_PIN, 1);
                sleep_us(100);  // Brief flash
                gpio_put(LED_PIN, 0);
            }
        }
        
        // Heartbeat every 500ms
        uint32_t now = to_ms_since_boot(get_absolute_time());
        if (now - last_blink >= 500) {
            led_state = !led_state;
            gpio_put(LED_PIN, led_state);
            last_blink = now;
        }
    }
}
