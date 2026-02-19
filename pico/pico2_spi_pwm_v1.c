#include "pico/stdlib.h"
#include "hardware/pwm.h"
#include "hardware/spi.h"
#include "hardware/gpio.h"
#include "hardware/dma.h" // NEW: DMA Library
#include <stdbool.h>

// ==========================================
// CONFIGURATION
// ==========================================
#define PICO_ID 0   
#define MOTORS_PER_PICO 9
static const uint MOTOR_PINS[MOTORS_PER_PICO] = {0, 1, 2, 3, 4, 5, 6, 7, 8};
#define LED_PIN 25

#define PWM_WRAP    31250
#define PWM_DIVIDER 64.0f

#define SPI_INST spi0
#define PIN_MISO 19 
#define PIN_CS   17 
#define PIN_SCK  18 
#define PIN_MOSI 16 

#define TOTAL_MOTORS 36
#define SYNC_PIN 22

// Globals
uint slices[MOTORS_PER_PICO];
uint channels[MOTORS_PER_PICO];

// DMA Buffer and Channel
uint8_t spi_rx_buffer[TOTAL_MOTORS];
int dma_chan;

volatile bool sync_pulse_detected = false;
volatile uint32_t sync_counter = 0;

// ==========================================
// PWM CONTROL
// ==========================================
void set_motor_pwm_us(uint motor_index, uint16_t pulse_us) {
    if (pulse_us < 1000) pulse_us = 1000;
    if (pulse_us > 2000) pulse_us = 2000;
    
    // FASTER INTEGER MATH: Replaces float math (pulse_us * 2.34375f)
    // pulse_us * 150 / 64 is mathematically identical and takes 1 CPU cycle
    uint32_t level = (pulse_us * 150) / 64;
    
    if (level > PWM_WRAP) level = PWM_WRAP;
    pwm_set_chan_level(slices[motor_index], channels[motor_index], (uint16_t)level);
}

// ==========================================
// INTERRUPT HANDLER
// ==========================================
void sync_irq_handler(uint gpio, uint32_t events) {
    if (gpio == SYNC_PIN) {
        sync_pulse_detected = true;
        
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
    // 1. Initialize LED & PWMs
    gpio_init(LED_PIN);
    gpio_set_dir(LED_PIN, GPIO_OUT);
    gpio_put(LED_PIN, 1);

    for (uint i = 0; i < MOTORS_PER_PICO; i++) {
        gpio_set_function(MOTOR_PINS[i], GPIO_FUNC_PWM);
        slices[i] = pwm_gpio_to_slice_num(MOTOR_PINS[i]);
        channels[i] = pwm_gpio_to_channel(MOTOR_PINS[i]);

        pwm_set_clkdiv(slices[i], PWM_DIVIDER);
        pwm_set_wrap(slices[i], PWM_WRAP);
        pwm_set_enabled(slices[i], true);
        set_motor_pwm_us(i, 1000); 
    }

    // 2. Initialize SPI (Slave)
    spi_init(SPI_INST, 1000000);
    spi_set_slave(SPI_INST, true);
    gpio_set_function(PIN_MISO, GPIO_FUNC_SPI);
    gpio_set_function(PIN_CS,   GPIO_FUNC_SPI);
    gpio_set_function(PIN_SCK,  GPIO_FUNC_SPI);
    gpio_set_function(PIN_MOSI, GPIO_FUNC_SPI);

    // 3. --- INITIALIZE DMA ---
    // This tells the hardware to automatically route SPI bytes into our spi_rx_buffer
    dma_chan = dma_claim_unused_channel(true);
    dma_channel_config c = dma_channel_get_default_config(dma_chan);
    
    channel_config_set_transfer_data_size(&c, DMA_SIZE_8); // 8-bit transfers
    channel_config_set_dreq(&c, spi_get_dreq(SPI_INST, false)); // Trigger on SPI RX
    channel_config_set_read_increment(&c, false); // Keep reading from SPI Data Register
    channel_config_set_write_increment(&c, true); // Increment our array index
    
    dma_channel_configure(
        dma_chan,
        &c,
        spi_rx_buffer,             // Write straight to our array
        &spi_get_hw(SPI_INST)->dr, // Read straight from hardware SPI register
        TOTAL_MOTORS,              // Stop after 36 bytes
        true                       // Start waiting for bytes immediately
    );

    // 4. Initialize Sync Pin
    gpio_init(SYNC_PIN);
    gpio_set_dir(SYNC_PIN, GPIO_IN);
    gpio_pull_down(SYNC_PIN); 
    gpio_set_irq_enabled_with_callback(SYNC_PIN, GPIO_IRQ_EDGE_RISE, true, &sync_irq_handler);

    const int MY_START = PICO_ID * MOTORS_PER_PICO;
    absolute_time_t last_sync_time = get_absolute_time();
    const uint64_t SAFETY_TIMEOUT_US = 200000;

    while (true) {
        
        // --- APPLY ON SYNC ---
        if (sync_pulse_detected) {
            sync_pulse_detected = false;
            last_sync_time = get_absolute_time();
            
            // 1. Apply the data the DMA hardware collected for us
            for (uint i = 0; i < MOTORS_PER_PICO; i++) {
                uint8_t raw_val = spi_rx_buffer[MY_START + i];
                
                uint16_t target_pwm = (raw_val == 0) ? 1000 : 1200 + ((uint32_t)raw_val * 800) / 255;
                set_motor_pwm_us(i, target_pwm);
            }
            
            // 2. Reset the DMA so it writes to the beginning of the buffer for the next frame
            dma_channel_set_write_addr(dma_chan, spi_rx_buffer, true);
            
            // 3. Flush any leftover garbage in the hardware FIFO (prevents misalignment)
            while(spi_is_readable(SPI_INST)) {
                (void)spi_get_hw(SPI_INST)->dr;
            }
        }

        // --- SAFETY WATCHDOG ---
        if (absolute_time_diff_us(last_sync_time, get_absolute_time()) > SAFETY_TIMEOUT_US) {
            for (uint i = 0; i < MOTORS_PER_PICO; i++) {
                set_motor_pwm_us(i, 1000);
            }
            gpio_put(LED_PIN, (to_ms_since_boot(get_absolute_time()) % 200) < 100);
            
            // If we timed out, force reset the DMA channel just in case
            dma_channel_abort(dma_chan);
            dma_channel_set_write_addr(dma_chan, spi_rx_buffer, true);
        }
    }
}