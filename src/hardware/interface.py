"""
Hardware Abstraction Layer for cross-platform compatibility.
Updated for Shared SPI (Broadcast Mode) - No Chip Selects.
"""

import platform
from typing import List, Optional, Dict
import numpy as np
from config import MOTOR_TO_PICO_LOOKUP, PICO_MOTOR_MAP, PWM_MIN, PWM_MAX

PACKET_START = 0xAA
PACKET_END = 0x55

class MockSPI:
    """Mock SPI interface for macOS development."""
    def __init__(self):
        self.frame_count = 0
    
    def write_bytes(self, data: List[int]) -> None:
        self.frame_count += 1
    
    def close(self) -> None:
        pass

class MockGPIO:
    """Mock GPIO interface for macOS development."""
    def __init__(self):
        self.frame_count = 0
    
    def toggle_sync_pin(self) -> None:
        self.frame_count += 1
        if self.frame_count % 100 == 0:
            print(f"[GPIO] Sync Pin Toggled (frame {self.frame_count})")

class RealSPI:
    """Real SPI interface for Raspberry Pi using SPI0."""
    def __init__(self):
        import spidev # type: ignore
        self.spi = spidev.SpiDev()
        # Open SPI0.0. Note: This CLAIMS GPIO 8 (CE0) automatically!
        self.spi.open(0, 0)
        self.spi.max_speed_hz = 1000000  # 1 MHz
        self.spi.mode = 1
        self.spi.bits_per_word = 8
        print("[SPI] Initialized SPI0 (GPIO10=MOSI, GPIO11=SCLK)")
    
    def write_bytes(self, data: List[int]) -> None:
        self.spi.writebytes(data)
    
    def close(self) -> None:
        self.spi.close()

class RealGPIO:
    """Real GPIO interface using gpiod. ONLY handles the Sync Pin."""
    def __init__(self, sync_pin: int = 22):
        import gpiod # type: ignore
        from gpiod.line import Direction, Value # type: ignore
        import time
        
        self.gpiod = gpiod
        self.Value = Value
        self.time = time
        self.sync_pin = sync_pin
        self.gpio_chip = '/dev/gpiochip4'  # Pi 5 uses gpiochip4
        
        # FIX: We ONLY request the Sync Pin. We DO NOT request CS pins (GPIO 8/7/etc).
        # This prevents the "Device or resource busy" error.
        config = {
            sync_pin: gpiod.LineSettings(direction=Direction.OUTPUT)
        }
        
        try:
            self.line_request = gpiod.request_lines(
                self.gpio_chip,
                consumer="wind-wall-control",
                config=config
            )
            # Initialize sync pin to LOW
            self.line_request.set_value(self.sync_pin, Value.INACTIVE)
            print(f"[GPIO] Using gpiod (Pi 5) - Sync pin initialized on GPIO {self.sync_pin}")
            
        except OSError as e:
            print(f"[GPIO] CRITICAL ERROR: Could not claim GPIO {sync_pin}. {e}")
            raise e
    
    def toggle_sync_pin(self) -> None:
        """Toggle the GPIO sync pin with a 10µs pulse."""
        self.line_request.set_value(self.sync_pin, self.Value.ACTIVE)
        self.time.sleep(0.00001)  # 10 microsecond pulse
        self.line_request.set_value(self.sync_pin, self.Value.INACTIVE)

class HardwareInterface:
    """
    Hardware abstraction layer for Wind Wall.
    Architecture: Shared SPI Broadcast (No CS) + Shared Sync Trigger.
    """
    
    def __init__(self, use_mock: Optional[bool] = None):
        self.platform = platform.system()
        
        if use_mock is None:
            self.use_mock = self.platform == "Darwin"
        else:
            self.use_mock = use_mock
            
        self.motor_to_pico_lookup = MOTOR_TO_PICO_LOOKUP
        self.frames_sent = 0
        
        self._init_drivers()
        print(f"[HW] Interface Ready. Mode: {'MOCK' if self.use_mock else 'REAL'}")

    def _init_drivers(self) -> None:
        """Initialize SPI and GPIO drivers."""
        if self.use_mock:
            print(f"[HW] Running on {self.platform} with MOCK drivers")
            self.spi = MockSPI()
            self.gpio = MockGPIO()
        else:
            print(f"[HW] Running on {self.platform} with REAL drivers")
            try:
                self.spi = RealSPI()
                # FIX: Do not pass CS pins here.
                self.gpio = RealGPIO(sync_pin=22)
            except Exception as e:
                print(f"[HW] Failed to init real drivers: {e}, falling back to mock")
                self.use_mock = True
                self.spi = MockSPI()
                self.gpio = MockGPIO()

    def send_pwm(self, pwm_values: np.ndarray) -> None:
        """
        Send PWM values to ALL Picos in one Broadcast Frame.
        Packet: [0xAA, M0_H, M0_L, ... M35_H, M35_L, 0x55]
        """
        self.frames_sent += 1
        

        packet = []
        for pwm in pwm_values:
            if pwm < 1200:
                byte_val = 0x00
            else:
                clipped = max(1200, min(2000, pwm))
                byte_val = 1 + int((clipped - 1200) * 254 / 800)
                byte_val = max(1, min(255, byte_val))
            packet.append(byte_val)
        # # 1. Build the Broadcast Packet
        # packet = [PACKET_START, 0x00]
        
        # # Flatten all 36 motors into the packet sequentially
        # # Assuming pwm_values is indexed 0..35
        # for pwm in pwm_values:
        # #     val = int(max(PWM_MIN, min(PWM_MAX, pwm)))
        # #     packet.append((val >> 8) & 0xFF) # High Byte
        # #     packet.append(val & 0xFF)        # Low Byte
        #     # 1. Clip the value to your range
        #     pwm_val = max(1200, min(2000, pwm))
        #     # 2. Map 1200-2000 -> 0-255
        #     byte_val = int((pwm_val - 1200) * 255 / 800)

        #     # 3. Add to packet
        #     packet.append(byte_val)
        
        # packet.append(PACKET_END)

        # 2. Send Stream (No CS toggling needed)
        try:
            self.spi.write_bytes(packet)
        except Exception as e:
            print(f"[HW] SPI Write Error: {e}")
            
        # 3. Trigger Sync (Latches data on all Picos at once)
        try:
            self.gpio.toggle_sync_pin()
        except Exception as e:
            print(f"[HW] Sync Error: {e}")
        
        if self.frames_sent % 400 == 0:
            print(f"[HW] Frame {self.frames_sent}: Broadcast sent, sync triggered")

    def close(self) -> None:
        try:
            self.spi.close()
            print("[HW] SPI interface closed")
        except:
            pass