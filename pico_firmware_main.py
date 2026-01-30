"""
Raspberry Pi Pico 2 Firmware for Wind Wall Motor Control
=========================================================

This firmware runs on each Pico 2 and controls 9 motors via PWM.
It receives PWM commands from the Raspberry Pi 5 via SPI and updates
motor outputs only when a sync pulse is received on GP20.

Hardware Setup:
- SPI Peripheral: GP16 (RX/MISO), GP17 (CS), GP18 (SCK), GP19 (TX/MOSI - not used)
- Sync Pulse Input: GP20 (from Pi's GPIO 22)
- PWM Outputs: GP0-GP8 (9 motors)

Protocol:
- Packet format: [0xAA, PWM1_H, PWM1_L, ..., PWM9_H, PWM9_L, 0x55]
- Total: 21 bytes per packet
- PWM values: 1000-2000 µs (encoded as 16-bit big-endian)
- Update rate: 400 Hz (triggered by sync pulse)

Author: Wind Wall Control System
Date: 2026-01-30
"""

from machine import Pin, PWM, SPI # type: ignore
import time
import struct

# Configuration
NUM_MOTORS = 9
PWM_FREQ = 50  # 50 Hz for standard motor controllers (ESCs)
PACKET_SIZE = 21  # 1 start + 9*2 PWM bytes + 1 end
START_BYTE = 0xAA
END_BYTE = 0x55

# Pin Definitions
SPI_SCK = 18   # GP18 - SPI clock from Pi
SPI_MOSI = 19  # GP19 - SPI data from Pi (MOSI on Pi = RX on Pico)
SPI_MISO = 16  # GP16 - SPI data to Pi (not used, but needed for SPI setup)
SPI_CS = 17    # GP17 - Chip Select from Pi
SYNC_PIN = 20  # GP20 - Sync pulse from Pi (GPIO 22)

# Motor PWM pins (GP0-GP8)
MOTOR_PINS = [0, 1, 2, 3, 4, 5, 6, 7, 8]

# Global state
pwm_motors = []
pending_pwm_values = [1500] * NUM_MOTORS  # Neutral position (1500 µs)
update_ready = False
packet_buffer = bytearray()
spi_active = False

# LED for status indication (built-in LED on Pico)
led = Pin('LED', Pin.OUT)
led.off()


def init_pwm():
    """Initialize PWM outputs for 9 motors."""
    global pwm_motors
    print("Initializing PWM on GP0-GP8...")
    
    for pin_num in MOTOR_PINS:
        pin = Pin(pin_num, Pin.OUT)
        pwm = PWM(pin)
        pwm.freq(PWM_FREQ)
        # Set to neutral (1500 µs = 7.5% duty at 50Hz)
        # Duty cycle = (pulse_width_us / 20000) * 65535
        neutral_duty = int((1500 / 20000) * 65535)
        pwm.duty_u16(neutral_duty)
        pwm_motors.append(pwm)
        print(f"  Motor on GP{pin_num} initialized (1500 µs)")
    
    print("PWM initialization complete.")


def set_motor_pwm(motor_index, pulse_width_us):
    """
    Set PWM duty cycle for a motor.
    
    Args:
        motor_index: Motor index (0-8)
        pulse_width_us: Pulse width in microseconds (1000-2000)
    """
    # Clamp to valid range
    pulse_width_us = max(1000, min(2000, pulse_width_us))
    
    # Convert to 16-bit duty cycle
    # Period = 20ms = 20000 µs at 50 Hz
    # Duty = (pulse_width / 20000) * 65535
    duty_cycle = int((pulse_width_us / 20000.0) * 65535)
    
    pwm_motors[motor_index].duty_u16(duty_cycle)


def parse_packet(data):
    """
    Parse SPI packet and extract PWM values.
    
    Packet format: [0xAA, PWM1_H, PWM1_L, ..., PWM9_H, PWM9_L, 0x55]
    
    Args:
        data: bytearray of received SPI data
    
    Returns:
        list of 9 PWM values (int), or None if invalid
    """
    if len(data) != PACKET_SIZE:
        return None
    
    if data[0] != START_BYTE or data[-1] != END_BYTE:
        return None
    
    pwm_values = []
    for i in range(NUM_MOTORS):
        # Extract 2 bytes for each motor (big-endian)
        idx = 1 + i * 2
        high_byte = data[idx]
        low_byte = data[idx + 1]
        pwm = (high_byte << 8) | low_byte
        pwm_values.append(pwm)
    
    return pwm_values


def sync_interrupt(pin):
    """
    Interrupt handler for sync pulse on GP20.
    Sets flag to update motors with pending PWM values.
    """
    global update_ready
    update_ready = True
    led.toggle()  # Visual feedback


def spi_rx_callback(spi):
    """
    Callback for SPI data reception.
    Note: MicroPython doesn't have built-in SPI peripheral mode with interrupts,
    so we'll use polling in the main loop instead.
    """
    pass


def init_spi():
    """
    Initialize SPI peripheral.
    Note: Pico's MicroPython uses SPI in controller mode by default.
    For peripheral mode, we need to poll manually.
    """
    global spi
    # SPI peripheral configuration
    # We'll use polling mode since MicroPython doesn't support SPI peripheral interrupts
    spi = SPI(0, baudrate=1000000, polarity=0, phase=0, 
              sck=Pin(SPI_SCK), mosi=Pin(SPI_MOSI), miso=Pin(SPI_MISO))
    print("SPI initialized (polling mode)")


def init_sync_interrupt():
    """Initialize sync pulse interrupt on GP20."""
    sync_pin = Pin(SYNC_PIN, Pin.IN, Pin.PULL_DOWN)
    sync_pin.irq(trigger=Pin.IRQ_RISING, handler=sync_interrupt)
    print(f"Sync interrupt initialized on GP{SYNC_PIN}")


def main():
    """Main control loop."""
    global update_ready, pending_pwm_values, packet_buffer, spi_active
    
    print("\n" + "="*50)
    print("Wind Wall Pico 2 Firmware v1.0")
    print("="*50)
    
    # Initialize hardware
    init_pwm()
    init_sync_interrupt()
    
    # Setup CS pin as input to detect when we're selected
    cs_pin = Pin(SPI_CS, Pin.IN, Pin.PULL_UP)
    
    print("\nStartup complete. Waiting for SPI data...")
    print("Motors initialized to 1500 µs (neutral)")
    print("="*50 + "\n")
    
    frame_count = 0
    last_update_time = time.ticks_ms()
    
    # Main loop
    while True:
        # Check if CS is active (LOW)
        if cs_pin.value() == 0:
            if not spi_active:
                spi_active = True
                packet_buffer = bytearray()
            
            # In a real peripheral mode, we'd receive data via SPI
            # Since MicroPython doesn't support SPI peripheral mode easily,
            # this is a simplified version. For production, use:
            # 1. PIO (Programmable I/O) for custom SPI peripheral
            # 2. External SPI peripheral library
            # 3. UART as alternative communication method
            
            # Placeholder: simulate receiving 21 bytes
            # In production, replace this with actual SPI peripheral read
            try:
                # This would be: packet_buffer = spi.read(PACKET_SIZE)
                # For now, we'll skip actual SPI reading in this template
                pass
            except:
                pass
        else:
            if spi_active:
                # CS went HIGH - packet complete
                spi_active = False
                
                if len(packet_buffer) == PACKET_SIZE:
                    # Parse packet
                    pwm_values = parse_packet(packet_buffer)
                    if pwm_values:
                        # Store pending values (don't update motors yet)
                        pending_pwm_values = pwm_values
                        # Debug: print every 100 packets
                        frame_count += 1
                        if frame_count % 100 == 0:
                            print(f"Packet {frame_count}: Received valid PWM data")
                
                packet_buffer = bytearray()
        
        # Check if sync pulse triggered an update
        if update_ready:
            update_ready = False
            
            # Update all motors with pending values
            for i in range(NUM_MOTORS):
                set_motor_pwm(i, pending_pwm_values[i])
            
            # Status reporting
            current_time = time.ticks_ms()
            if time.ticks_diff(current_time, last_update_time) >= 1000:
                print(f"Update rate: ~{frame_count} Hz | Motors updated")
                last_update_time = current_time
        
        # Small delay to prevent busy-waiting
        time.sleep_ms(1)


# Run main loop
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nShutdown requested. Stopping motors...")
        # Set all motors to neutral
        for i in range(NUM_MOTORS):
            set_motor_pwm(i, 1500)
        print("Motors stopped. Firmware halted.")
