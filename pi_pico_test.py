import spidev
import gpiod
import time

# --- CONFIGURATION ---
TRIGGER_PIN_BCM = 25  # GPIO 25 (Physical Pin 22)
SPI_BUS = 0
SPI_DEVICE = 0

# --- 1. SETUP GPIOD (The Trigger) ---
# On Raspberry Pi 5, the header is usually on 'gpiochip4'
chip = gpiod.Chip('gpiochip4') 
trigger_line = chip.get_line(TRIGGER_PIN_BCM)

# Request the line as an OUTPUT
req = gpiod.line_request()
req.consumer = "PicoTrigger"
req.request_type = gpiod.LINE_REQ_DIR_OUT
trigger_line.request(req)

# Ensure we start LOW
trigger_line.set_value(0)

# --- 2. SETUP SPI (The Loader) ---
spi = spidev.SpiDev()
spi.open(SPI_BUS, SPI_DEVICE)
spi.max_speed_hz = 1000000 

print(f"System Active. Using GPIO {TRIGGER_PIN_BCM} on {chip.name()} as Trigger.")
print("Sending Data... Motor updates on Trigger pulse.")

try:
    val = 0
    direction = 1
    
    while True:
        # A. LOAD: Send Data over SPI
        # Pico stores this in 'next_pwm_val' but DOES NOT move motor
        spi.xfer2([val])
        
        # Tiny pause to ensure SPI transaction is complete 
        # (This is conservative; SPI is very fast)
        time.sleep(0.0001)

        # B. FIRE: Pulse the Trigger Line
        # 1. Set High (Trigger Interrupt)
        trigger_line.set_value(1)
        # 2. Hold for a microsecond (Pico is fast, this is plenty)
        time.sleep(0.0001) 
        # 3. Set Low (Reset)
        trigger_line.set_value(0)

        # Visual feedback
        if val % 50 == 0: 
            print(f"Loaded: {val} -> FIRED!")

        # Ramp Logic (0 -> 255 -> 0)
        val += 5 * direction
        if val >= 255 or val <= 0:
            direction *= -1
            
        # Update Rate (e.g., 20Hz)
        time.sleep(0.05) 

except KeyboardInterrupt:
    print("\nStopping...")
    spi.close()
    trigger_line.release()
    chip.close()