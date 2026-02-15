#include "pico/stdlib.h"
#include "hardware/pwm.h"
#include "hardware/spi.h"

#define MOTOR_PIN 14
#define SPI_PORT spi0
#define PIN_CS   17
#define PIN_SCK  18
#define PIN_MOSI 19

// Simple test to verify SPI slave reception and PWM output control on a single pin (GP14) with LED (GP25) to indicate the program is running
#define LED_PIN 25

int main() {
    // Initialize LED pin
    gpio_init(LED_PIN);
    gpio_set_dir(LED_PIN, GPIO_OUT);

    // Initialize PWM output on MOTOR_PIN
    gpio_set_function(MOTOR_PIN, GPIO_FUNC_PWM);
    uint slice_num = pwm_gpio_to_slice_num(MOTOR_PIN);
    pwm_set_clkdiv(slice_num, 6.0f);
    pwm_set_wrap(slice_num, 24999);
    pwm_set_enabled(slice_num, true);

    // Initialize SPI slave
    spi_init(SPI_PORT, 1000000); // Set to 1 MHz [6]
    spi_set_slave(SPI_PORT, true); // Configure as slave [6]

    // Map the physical pins to the SPI hardware
    gpio_set_function(PIN_CS,   GPIO_FUNC_SPI); 
    gpio_set_function(PIN_SCK,  GPIO_FUNC_SPI); 
    gpio_set_function(PIN_MOSI, GPIO_FUNC_SPI); 

    uint8_t rx_byte;

    while (true) {
        // This function halts the Pico and waits until the Pi 5 sends data
        spi_read_blocking(SPI_PORT, 0, &rx_byte, 1); 

        // We received a byte (0 to 255). 
        // Let's scale it to our PWM range (0 to 25000)
        uint32_t new_duty_cycle = (rx_byte * 25000) / 255;
        
        // Update the motor output
        pwm_set_chan_level(slice_num, pwm_gpio_to_channel(MOTOR_PIN), new_duty_cycle);

        // Flash LED to indicate program is running and data was received
        gpio_put(LED_PIN, 1); 
        sleep_ms(100);
        gpio_put(LED_PIN, 0); 
        sleep_ms(100);
    }
}