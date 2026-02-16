#include "pico/stdlib.h"
#include "hardware/pwm.h"
#include "hardware/spi.h"

// === CONFIGURATION ===
#define SPI_PORT spi0
#define SPI_RX_PIN 16   // GPIO16 (MOSI)
#define SPI_CSN_PIN 17  // GPIO17 (CS)
#define SPI_SCK_PIN 18  // GPIO18 (Clock)

// Motor PWM outputs (can control multiple motors)
#define MOTOR1_PIN 14   // GPIO14 for Motor 1 (default test motor)
#define MOTOR2_PIN 15   // GPIO15 for Motor 2

// === PWM CONFIGURATION ===
// For servo-style PWM (1000-2000 µs range at 50 Hz):
// - Clock divider: 150 (125MHz / 150 = 833.33 kHz)
// - Wrap: 15999 (833.33 kHz / 16000 = 52.08 Hz ≈ 50 Hz)
// - Level 1000 = 1.2 ms, Level 2000 = 2.4 ms
#define PWM_CLOCK_DIV 150.0f
#define PWM_WRAP 15999
#define PWM_MIN 1000
#define PWM_MAX 2000

// === VOLATILE STATE ===
volatile uint16_t pwm_value_m1 = 1500;  // Motor 1 current PWM value
volatile uint16_t pwm_value_m2 = 1500;  // Motor 2 current PWM value
volatile uint8_t received_byte = 0;
volatile uint32_t packet_count = 0;
volatile bool data_received = false;

uint slice_num_m1, slice_num_m2;

// === SPI INTERRUPT HANDLER ===
void spi_irq_handler() {
    if (spi_is_readable(SPI_PORT)) {
        // Read one byte
        uint8_t byte = spi_get_hw(SPI_PORT)->dr;
        received_byte = byte;
        data_received = true;
        
        // Map byte value (0-255) to PWM range (1000-2000)
        uint16_t pwm_level = PWM_MIN + ((uint32_t)byte * (PWM_MAX - PWM_MIN)) / 255;
        
        // Update both motors with the same value for simplicity
        // In a real scenario, you'd parse multi-byte packets to select which motor
        pwm_value_m1 = pwm_level;
        pwm_value_m2 = pwm_level;
        
        packet_count++;
    }
}

// === INITIALIZE MOTORS ===
void init_motors() {
    // Setup Motor 1 (GPIO14)
    gpio_set_function(MOTOR1_PIN, GPIO_FUNC_PWM);
    slice_num_m1 = pwm_gpio_to_slice_num(MOTOR1_PIN);
    pwm_set_clkdiv(slice_num_m1, PWM_CLOCK_DIV);
    pwm_set_wrap(slice_num_m1, PWM_WRAP);
    pwm_set_chan_level(slice_num_m1, pwm_gpio_to_channel(MOTOR1_PIN), pwm_value_m1);
    pwm_set_enabled(slice_num_m1, true);
    
    // Setup Motor 2 (GPIO15)
    gpio_set_function(MOTOR2_PIN, GPIO_FUNC_PWM);
    slice_num_m2 = pwm_gpio_to_slice_num(MOTOR2_PIN);
    pwm_set_clkdiv(slice_num_m2, PWM_CLOCK_DIV);
    pwm_set_wrap(slice_num_m2, PWM_WRAP);
    pwm_set_chan_level(slice_num_m2, pwm_gpio_to_channel(MOTOR2_PIN), pwm_value_m2);
    pwm_set_enabled(slice_num_m2, true);
}

// === INITIALIZE SPI SLAVE ===
void init_spi_slave() {
    // Initialize SPI at 1 MHz in slave mode
    spi_init(SPI_PORT, 1000 * 1000);
    spi_set_slave(SPI_PORT, true);
    
    // Setup GPIO pins for SPI
    gpio_set_function(SPI_RX_PIN, GPIO_FUNC_SPI);   // MOSI
    gpio_set_function(SPI_CSN_PIN, GPIO_FUNC_SPI);  // CS
    gpio_set_function(SPI_SCK_PIN, GPIO_FUNC_SPI);  // Clock
    
    // Enable SPI RX interrupt
    hw_set_bits(&spi_get_hw(SPI_PORT)->imsc, SPI_SSPIMSC_RXIM_BITS);
    irq_set_exclusive_handler(SPI0_IRQ, spi_irq_handler);
    irq_set_enabled(SPI0_IRQ, true);
}

// === MAIN LOOP ===
int main() {
    stdio_init_all();
    
    // Initialize components
    init_motors();
    init_spi_slave();
    
    printf("\n========================================\n");
    printf("Pico Test v5 - SPI Slave PWM Control\n");
    printf("========================================\n");
    printf("Motor 1: GPIO14, PWM range 1000-2000µs\n");
    printf("Motor 2: GPIO15, PWM range 1000-2000µs\n");
    printf("SPI Slave Mode: 1 MHz, Mode 0\n");
    printf("GPIO17: CS, GPIO16: MOSI, GPIO18: Clock\n");
    printf("========================================\n\n");
    
    uint32_t last_packet_count = 0;
    uint32_t update_counter = 0;
    
    while (true) {
        // Check if new data was received
        if (data_received) {
            data_received = false;
            
            // Update PWM outputs with the new values
            pwm_set_chan_level(slice_num_m1, pwm_gpio_to_channel(MOTOR1_PIN), pwm_value_m1);
            pwm_set_chan_level(slice_num_m2, pwm_gpio_to_channel(MOTOR2_PIN), pwm_value_m2);
        }
        
        // Print status every 100ms
        if (++update_counter % 100 == 0) {
            if (packet_count != last_packet_count) {
                last_packet_count = packet_count;
                
                // Calculate pulse width in microseconds for display
                float pwm_us_m1 = (pwm_value_m1 / 16000.0f) * 1000.0f;
                float pwm_us_m2 = (pwm_value_m2 / 16000.0f) * 1000.0f;
                
                printf("Packet #%lu | M1: %u (%.1fµs) M2: %u (%.1fµs) | Raw: 0x%02X\n",
                       packet_count, pwm_value_m1, pwm_us_m1, pwm_value_m2, pwm_us_m2, received_byte);
            }
        }
        
        sleep_ms(1);
    }
    
    return 0;
}
