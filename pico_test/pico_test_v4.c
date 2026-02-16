#include "pico/stdlib.h"
#include "hardware/pwm.h"
#include "hardware/spi.h"
#include "hardware/irq.h"

#define MOTOR_PIN 15
#define SPI_PORT spi0
#define PIN_RX  16 
#define PIN_CSN 17 
#define PIN_SCK 18 

// NEW: The Dedicated Trigger Pin
#define TRIGGER_PIN 20 

// Variables shared between Main Loop and Interrupt
volatile uint16_t next_pwm_val = 1500; // The "Next" value waiting to be loaded
uint slice_num; 

// --- THE INTERRUPT HANDLER (The "Fire" Command) ---
// This runs AUTOMATICALY when TRIGGER_PIN goes High.
void trigger_handler(uint gpio, uint32_t events) {
    // Apply the value we have sitting in the waiting room
    pwm_set_chan_level(slice_num, pwm_gpio_to_channel(MOTOR_PIN), next_pwm_val);
}

int main() {
    // 1. SETUP PWM
    gpio_set_function(MOTOR_PIN, GPIO_FUNC_PWM);
    slice_num = pwm_gpio_to_slice_num(MOTOR_PIN);
    pwm_set_clkdiv(slice_num, 150.0f); 
    pwm_set_wrap(slice_num, 15999);    
    pwm_set_chan_level(slice_num, pwm_gpio_to_channel(MOTOR_PIN), 1500);
    pwm_set_enabled(slice_num, true);

    // 2. SETUP TRIGGER PIN
    gpio_init(TRIGGER_PIN);
    gpio_set_dir(TRIGGER_PIN, GPIO_IN);
    // Attach interrupt to the Rising Edge (Low -> High)
    gpio_set_irq_enabled_with_callback(TRIGGER_PIN, GPIO_IRQ_EDGE_RISE, true, &trigger_handler);

    // 3. SETUP SPI SLAVE
    spi_init(SPI_PORT, 1000 * 1000);
    spi_set_slave(SPI_PORT, true);
    gpio_set_function(PIN_RX, GPIO_FUNC_SPI);
    gpio_set_function(PIN_CSN, GPIO_FUNC_SPI);
    gpio_set_function(PIN_SCK, GPIO_FUNC_SPI);

    uint8_t received_val = 0;

    // 4. MAIN LOOP (The "Loading" Zone)
    while (true) {
        // We just listen for data constantly.
        // We do NOT update the motor here. We only update the "next_pwm_val" variable.
        if (spi_is_readable(SPI_PORT)) {
            spi_read_blocking(SPI_PORT, 0, &received_val, 1);
            
            // Map and Store (Do not Apply)
            next_pwm_val = 1000 + ((uint32_t)received_val * 1000) / 255;
        }
    }
}