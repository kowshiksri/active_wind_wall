"""
Hardware Abstraction Layer for cross-platform compatibility.
Detects OS and provides real or mock hardware interfaces.
Simplified for 4-Pico SPI communication with manual chip select.
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
        """Initialize the mock SPI interface."""
        self.frame_count = 0
    
    def write_bytes(self, data: List[int]) -> None:
        """
        Simulate SPI write operation.
        
        Args:
            data: List of bytes to write
        """
        self.frame_count += 1
    
    def close(self) -> None:
        """Close the mock SPI interface."""
        pass


class MockGPIO:
    """Mock GPIO interface for macOS development."""
    
    def __init__(self):
        """Initialize the mock GPIO interface."""
        self.frame_count = 0
        self.cs_pins = {}
    
    def setup_cs_pin(self, pin: int) -> None:
        """Mock CS pin setup."""
        self.cs_pins[pin] = 'LOW'
    
    def set_cs_high(self, pin: int) -> None:
        """Mock CS pin high."""
        self.cs_pins[pin] = 'HIGH'
    
    def set_cs_low(self, pin: int) -> None:
        """Mock CS pin low."""
        self.cs_pins[pin] = 'LOW'
    
    def toggle_sync_pin(self) -> None:
        """
        Simulate sync pin toggle (print only once per 100 frames to reduce spam).
        """
        self.frame_count += 1
        if self.frame_count % 100 == 0:
            print(f"[GPIO] Sync Pin Toggled (frame {self.frame_count})")


class RealSPI:
    """Real SPI interface for Raspberry Pi using SPI0 (GPIO 10 MOSI, GPIO 11 SCLK)."""
    
    def __init__(self):
        """
        Initialize real SPI interface on SPI0.
        Uses GPIO 10 (MOSI) and GPIO 11 (SCLK).
        """
        import spidev # type: ignore
        self.spi = spidev.SpiDev()
        # Use SPI0, CE0 (we'll control CS manually, so CE doesn't matter)
        self.spi.open(0, 0)
        self.spi.max_speed_hz = 1000000  # 1 MHz
        self.spi.mode = 0  # SPI Mode 0 (CPOL=0, CPHA=0)
        self.spi.bits_per_word = 8
        print("[SPI] Initialized SPI0 (GPIO10=MOSI, GPIO11=SCLK)")
    
    def write_bytes(self, data: List[int]) -> None:
        """
        Write bytes via SPI.
        
        Args:
            data: List of bytes to write
        """
        self.spi.writebytes(data)
    
    def close(self) -> None:
        """Close the SPI interface."""
        self.spi.close()


class RealGPIO:
    """Real GPIO interface for Raspberry Pi 5 using gpiod."""
    
    def __init__(self, sync_pin: int = 22, cs_pins: Dict[int, int] = None):
        """
        Initialize real GPIO interface using gpiod (Pi 5 compatible).
        
        Args:
            sync_pin: GPIO pin number for sync signal (default: GPIO 22)
            cs_pins: Dict mapping pico_id to GPIO pin for chip select
        """
        import gpiod # type: ignore
        from gpiod.line import Direction, Value # type: ignore
        import time
        
        self.gpiod = gpiod
        self.Direction = Direction
        self.Value = Value
        self.time = time
        self.sync_pin = sync_pin
        self.cs_pins = cs_pins or {0: 8, 1: 7, 2: 17, 3: 27}
        self.gpio_chip = '/dev/gpiochip4'  # Pi 5 uses gpiochip4
        
        # Build configuration for all output pins
        all_pins = [sync_pin] + list(self.cs_pins.values())
        config = {}
        for pin in all_pins:
            config[pin] = gpiod.LineSettings(direction=Direction.OUTPUT)
        
        # Request all GPIO lines and keep the request open
        # Note: Unlike the context manager examples, we keep this persistent
        self.line_request = gpiod.request_lines(
            self.gpio_chip,
            consumer="wind-wall-control",
            config=config
        )
        
        # Initialize sync pin to LOW
        self.line_request.set_value(self.sync_pin, Value.INACTIVE)
        print(f"[GPIO] Using gpiod (Pi 5) - Sync pin initialized on GPIO {self.sync_pin}")
        
        # Initialize CS pins to HIGH (deselected)
        for pico_id, cs_pin in self.cs_pins.items():
            self.line_request.set_value(cs_pin, Value.ACTIVE)
            print(f"[GPIO] CS pin for Pico {pico_id} on GPIO {cs_pin}")
    
    def setup_cs_pin(self, pin: int) -> None:
        """Already handled in __init__"""
        pass
    
    def set_cs_high(self, pin: int) -> None:
        """Set CS pin HIGH (deselect)."""
        self.line_request.set_value(pin, self.Value.ACTIVE)
    
    def set_cs_low(self, pin: int) -> None:
        """Set CS pin LOW (select)."""
        self.line_request.set_value(pin, self.Value.INACTIVE)
    
    def toggle_sync_pin(self) -> None:
        """Toggle the GPIO sync pin with a 10µs pulse."""
        self.line_request.set_value(self.sync_pin, self.Value.ACTIVE)
        self.time.sleep(0.00001)  # 10 microsecond pulse
        self.line_request.set_value(self.sync_pin, self.Value.INACTIVE)


class HardwareInterface:
    """
    Hardware abstraction layer for 4-Pico Wind Wall control.
    Uses SPI0 (GPIO 10 MOSI, GPIO 11 SCLK) with manual chip select on:
    - Pico 0: GPIO 8
    - Pico 1: GPIO 7
    - Pico 2: GPIO 17
    - Pico 3: GPIO 27
    Sync pulse on GPIO 22.
    """
    
    def __init__(self, use_mock: Optional[bool] = None):
        """
        Initialize the hardware interface with platform detection.
        
        Args:
            use_mock: Force mock mode if True, auto-detect if None
        """
        self.platform = platform.system()
        
        # Force mock mode if requested, or auto-detect for macOS
        if use_mock is None:
            self.use_mock = self.platform == "Darwin"  # macOS
        else:
            self.use_mock = use_mock
        
        # CS pin assignments for each Pico
        self.cs_pins = {
            0: 8,   # Pico 0 -> GPIO 8
            1: 7,   # Pico 1 -> GPIO 7
            2: 17,  # Pico 2 -> GPIO 17
            3: 27   # Pico 3 -> GPIO 27
        }
        
        # Motor-to-Pico mapping from config
        self.motor_to_pico_lookup = MOTOR_TO_PICO_LOOKUP
        self.pico_motor_map = PICO_MOTOR_MAP
        
        # Build pico_id → list of motor_ids mapping
        self.pico_id_to_motors: Dict[int, List[int]] = {}
        for quadrant, config in self.pico_motor_map.items():
            pico_id = config['pico_id']
            if pico_id not in self.pico_id_to_motors:
                self.pico_id_to_motors[pico_id] = []
            self.pico_id_to_motors[pico_id].extend(config['motors'])
        
        # Statistics
        self.frames_sent = 0
        
        self._init_drivers()
        self._print_mapping_info()
    
    def _print_mapping_info(self) -> None:
        """Print mapping information at startup."""
        print("\n" + "="*70)
        print("[HW] 4-Pico Wind Wall Configuration:")
        print("="*70)
        print(f"SPI: GPIO 10 (MOSI), GPIO 11 (SCLK)")
        print(f"Chip Select Pins: Pico0=GPIO8, Pico1=GPIO7, Pico2=GPIO17, Pico3=GPIO27")
        print(f"Sync Pulse: GPIO 22")
        print("="*70)
        for quadrant, config in self.pico_motor_map.items():
            pico_id = config['pico_id']
            motors = config['motors']
            pin_offset = config['pin_offset']
            desc = config.get('description', '')
            cs_gpio = self.cs_pins[pico_id]
            print(f"  {desc:<25} → Pico{pico_id} (CS=GPIO{cs_gpio:2d}) | Motors {motors[0]:2d}-{motors[-1]:2d} | "
                  f"Pico Pins GP{pin_offset}-GP{pin_offset + len(motors) - 1}")
        print("="*70 + "\n")
    
    def _init_drivers(self) -> None:
        """Initialize SPI and GPIO drivers based on platform."""
        if self.use_mock:
            print(f"[HW] Running on {self.platform} with MOCK drivers")
            self.spi = MockSPI()
            self.gpio = MockGPIO()
            # Setup mock CS pins
            for pico_id, cs_pin in self.cs_pins.items():
                self.gpio.setup_cs_pin(cs_pin)
        else:
            print(f"[HW] Running on {self.platform} with REAL drivers")
            try:
                self.spi = RealSPI()
                self.gpio = RealGPIO(sync_pin=22, cs_pins=self.cs_pins)
            except Exception as e:
                print(f"[HW] Failed to init real drivers: {e}, falling back to mock")
                self.use_mock = True
                self.spi = MockSPI()
                self.gpio = MockGPIO()
                for pico_id, cs_pin in self.cs_pins.items():
                    self.gpio.setup_cs_pin(cs_pin)
    
    def _build_pico_packet(self, pwm_values: np.ndarray, pico_id: int) -> List[int]:
        """
        Build a 21-byte packet for one Pico: [0xAA, PWM1_H, PWM1_L, ..., PWM9_H, PWM9_L, 0x55].
        
        Args:
            pwm_values: Full array of 36 PWM values
            pico_id: Which Pico (0-3)
        
        Returns:
            List of 21 bytes
        """
        packet = [PACKET_START]  # Start byte
        
        # Get motor IDs for this Pico
        motor_ids = self.pico_id_to_motors.get(pico_id, [])
        
        # Extract 9 PWM values for this Pico's motors
        for motor_id in motor_ids:
            pwm = int(pwm_values[motor_id])
            # Clamp to valid range
            pwm = max(PWM_MIN, min(PWM_MAX, pwm))
            # Split into 2 bytes (big-endian)
            high_byte = (pwm >> 8) & 0xFF
            low_byte = pwm & 0xFF
            packet.extend([high_byte, low_byte])
        
        packet.append(PACKET_END)  # End byte
        
        return packet
    
    def send_pwm(self, pwm_values: np.ndarray) -> None:
        """
        Send PWM values to all Picos using a single broadcast SPI frame.
        Then trigger sync pulse on GPIO 22.
        
        Args:
            pwm_values: numpy array of shape (36,) with PWM values (1000-2000)
        """
        self.frames_sent += 1
        
        # Build a single broadcast packet for all 36 motors
        packet: List[int] = [PACKET_START]
        for motor_id in range(36):
            pwm = int(pwm_values[motor_id])
            pwm = max(PWM_MIN, min(PWM_MAX, pwm))
            high_byte = (pwm >> 8) & 0xFF
            low_byte = pwm & 0xFF
            packet.extend([high_byte, low_byte])
        packet.append(PACKET_END)

        # Send packet via SPI (single transaction)
        try:
            self.spi.write_bytes(packet)
        except Exception as e:
            print(f"[HW] ERROR: Broadcast send failed: {e}")
        
        # Trigger sync pulse after broadcast frame is sent
        try:
            self.gpio.toggle_sync_pin()
        except Exception as e:
            print(f"[HW] ERROR: Sync pin toggle failed: {e}")
        
        # Log periodically
        if self.frames_sent % 400 == 0:  # Every 1 second at 400Hz
            print(f"[HW] Frame {self.frames_sent}: Sent to all 4 Picos, sync pulse triggered")
    
    def close(self) -> None:
        """Close hardware interfaces."""
        try:
            self.spi.close()
            print("[HW] SPI interface closed")
        except Exception as e:
            print(f"[HW] Error closing SPI: {e}")
        print("[HW] Hardware interface closed")
