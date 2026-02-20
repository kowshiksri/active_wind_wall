"""
Hardware Abstraction Layer for SPI motor control.
Supports both real Raspberry Pi hardware and mock drivers for development.
"""

import platform
import time
from typing import List, Optional
import numpy as np

# Physical motor-to-byte mapping based on actual wiring configuration
# This maps motor IDs (0-35) to byte positions (0-35) in the SPI packet
# Byte positions 0-8   → Pico 0 reads these
# Byte positions 9-17  → Pico 1 reads these
# Byte positions 18-26 → Pico 2 reads these
# Byte positions 27-35 → Pico 3 reads these
PHYSICAL_MOTOR_ORDER = [
    # Pico 0 (byte positions 0-8): motors in physical order
    0, 1, 2, 6, 7, 8, 12, 13, 14,
    
    # Pico 1 (byte positions 9-17): motors in physical order
    18, 19, 20, 24, 25, 26, 30, 31, 32,
    
    # Pico 2 (byte positions 18-26): motors in physical order
    3, 4, 5, 9, 10, 11, 15, 16, 17,
    
    # Pico 3 (byte positions 27-35): motors in physical order
    21, 22, 23, 27, 28, 29, 33, 34, 35
]

class MockSPI:
    """Mock SPI for development/testing on non-Pi systems."""
    
    def __init__(self):
        self.frame_count = 0
    
    def write_bytes(self, data: List[int]) -> None:
        """Simulate SPI write operation."""
        self.frame_count += 1
    
    def close(self) -> None:
        pass

class MockGPIO:
    """Mock GPIO for development/testing on non-Pi systems."""
    
    def __init__(self):
        self.frame_count = 0
    
    def toggle_sync_pin(self) -> None:
        """Simulate GPIO sync pulse."""
        self.frame_count += 1
        if self.frame_count % 100 == 0:
            print(f"[GPIO] Sync pulse {self.frame_count}")

class RealSPI:
    """Hardware SPI driver for Raspberry Pi (SPI0)."""
    
    def __init__(self):
        import spidev # type: ignore
        self.spi = spidev.SpiDev()
        self.spi.open(0, 0)  # SPI0, CE0
        self.spi.max_speed_hz = 1000000  # 1 MHz
        self.spi.mode = 0
        self.spi.bits_per_word = 8
        print("[SPI] Initialized SPI0 (GPIO10=MOSI, GPIO11=SCLK)")
    
    def write_bytes(self, data: List[int]) -> None:
        """Send bytes via SPI. Each byte triggers CS toggle for Pico sync."""
        for b in data:
            self.spi.xfer2([int(b) & 0xFF])

    def close(self) -> None:
        self.spi.close()

class RealGPIO:
    """Hardware GPIO driver using gpiod (Raspberry Pi 5)."""
    
    def __init__(self, sync_pin: int = 22):
        import gpiod # type: ignore
        from gpiod.line import Direction, Value # type: ignore
        import time
        
        self.gpiod = gpiod
        self.Value = Value
        self.time = time
        self.sync_pin = sync_pin
        self.gpio_chip = '/dev/gpiochip4'  # Pi 5 uses gpiochip4
        
        # Configure sync pin as output (CS pins handled by SPI driver)
        config = {
            sync_pin: gpiod.LineSettings(direction=Direction.OUTPUT)
        }
        
        try:
            self.line_request = gpiod.request_lines(
                self.gpio_chip,
                consumer="wind-wall-control",
                config=config
            )
            self.line_request.set_value(self.sync_pin, Value.INACTIVE)
            print(f"[GPIO] Initialized GPIO {self.sync_pin} (sync pulse)")
            
        except OSError as e:
            print(f"[GPIO] ERROR: Could not claim GPIO {sync_pin}: {e}")
            raise e
    
    def toggle_sync_pin(self) -> None:
        """Send 10µs sync pulse to trigger PWM latch on all Picos."""
        self.line_request.set_value(self.sync_pin, self.Value.ACTIVE)
        self.time.sleep(0.00001)  # 10 microsecond pulse
        self.line_request.set_value(self.sync_pin, self.Value.INACTIVE)

class HardwareInterface:
    """
    Main hardware abstraction layer.
    
    Architecture:
    - SPI broadcast: sends 36-byte frame to all Picos simultaneously
    - Sync pulse: triggers atomic PWM update on all Picos
    - Physical motor remapping: handles wiring configuration
    """
    
    def __init__(self, use_mock: Optional[bool] = None):
        self.platform = platform.system()
        
        # Auto-detect mock mode on macOS, or use explicit setting
        if use_mock is None:
            self.use_mock = self.platform == "Darwin"
        else:
            self.use_mock = use_mock
            
        self.frames_sent = 0
        
        self._init_drivers()
        print(f"[HW] Ready. Mode: {'MOCK' if self.use_mock else 'REAL'}")

    def _init_drivers(self) -> None:
        """Initialize SPI and GPIO drivers based on platform."""
        if self.use_mock:
            print(f"[HW] Using mock drivers ({self.platform})")
            self.spi = MockSPI()
            self.gpio = MockGPIO()
        else:
            print(f"[HW] Initializing hardware drivers...")
            try:
                self.spi = RealSPI()
                self.gpio = RealGPIO(sync_pin=22)
            except Exception as e:
                print(f"[HW] Hardware init failed: {e}")
                print(f"[HW] Falling back to mock drivers")
                self.use_mock = True
                self.spi = MockSPI()
                self.gpio = MockGPIO()

    def send_pwm(self, pwm_values: np.ndarray) -> None:
        """
        Send PWM values to ALL Picos in one Broadcast Frame.
        
        The input pwm_values array is in logical motor order (0-35).
        We remap it to physical wiring order before sending.
        
        Packet structure: 36 bytes, one per motor in physical order
        - Bytes 0-8   → Pico 0 (motors 0,1,2,6,7,8,12,13,14)
        - Bytes 9-17  → Pico 1 (motors 18,19,20,24,25,26,30,31,32)
        - Bytes 18-26 → Pico 2 (motors 3,4,5,9,10,11,15,16,17)
        - Bytes 27-35 → Pico 3 (motors 21,22,23,27,28,29,33,34,35)
        """
        self.frames_sent += 1
        
        # 1. Reorder motors to match physical wiring configuration
        reordered_pwm = np.array([pwm_values[i] for i in PHYSICAL_MOTOR_ORDER])
        
        # 2. Convert PWM values (1000-2000 us) to byte values (0-255)
        packet = []
        for pwm in reordered_pwm:
            if pwm < 1200:
                byte_val = 0x00
            else:
                clipped = max(1200, min(2000, pwm))
                byte_val = 1 + int((clipped - 1200) * 254 / 800)
                byte_val = max(1, min(255, byte_val))
            packet.append(byte_val)

        # 3. Send via SPI
        try:
            self.spi.write_bytes(packet)
        except Exception as e:
            print(f"[HW] SPI Write Error: {e}")
        
        # 4. Trigger Sync (latches data on all Picos at once)
        try:
            self.gpio.toggle_sync_pin()
        except Exception as e:
            print(f"[HW] Sync Error: {e}")
        
        if self.frames_sent % 400 == 0:
            print(f"[HW] Frame {self.frames_sent}: Broadcast sent, sync triggered")

    def close(self) -> None:
        """Cleanup hardware resources."""
        try:
            self.spi.close()
            print("[HW] SPI closed")
        except:
            pass