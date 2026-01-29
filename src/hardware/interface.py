"""
Hardware Abstraction Layer for cross-platform compatibility.
Detects OS and provides real or mock hardware interfaces.
Includes motor-to-Pico mapping for distributed hardware control.
"""

import platform
from typing import List, Optional, Dict, Tuple
import numpy as np
from config import MOTOR_TO_PICO_LOOKUP, PICO_MOTOR_MAP


class MockSPI:
    """Mock SPI interface for macOS development."""
    
    def __init__(self):
        """Initialize the mock SPI interface."""
        self.frame_count = 0
    
    def xfer3(self, pwm_values: List[int]) -> None:
        """
        Simulate SPI transfer (one-way, PWM only).
        
        Args:
            pwm_values: List of 36 PWM values (1000-2000)
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
    
    def toggle_sync_pin(self) -> None:
        """
        Simulate sync pin toggle (print only once per 100 frames to reduce spam).
        """
        self.frame_count += 1
        if self.frame_count % 100 == 0:
            print(f"[GPIO] Sync Pin Toggled (frame {self.frame_count})")


class RealSPI:
    """Real SPI interface for Linux/Raspberry Pi."""
    
    def __init__(self, bus: int = 0, device: int = 0):
        """
        Initialize real SPI interface.
        
        Args:
            bus: SPI bus number
            device: SPI device number
        """
        import spidev # type: ignore
        self.spi = spidev.SpiDev()
        self.spi.open(bus, device)
        self.spi.max_speed_hz = 1000000  # 1 MHz
        self.spi.mode = 0  # SPI Mode 0 (CPOL=0, CPHA=0)
        self.spi.bits_per_word = 8
    
    def xfer3(self, pwm_values: List[int]) -> None:
        """
        Transfer PWM values via SPI with proper packet formatting.
        
        Protocol:
          - Start byte: 0xAA (sync marker)
          - N motors × 2 bytes each (PWM as 16-bit big-endian)
          - End byte: 0x55 (packet terminator)
        
        Args:
            pwm_values: List of PWM values (1000-2000) for this Pico's motors
        """
        # Build packet: [START, PWM_HIGH_0, PWM_LOW_0, ..., PWM_HIGH_N, PWM_LOW_N, END]
        packet = [0xAA]  # Start byte
        
        for pwm in pwm_values:
            # Clamp PWM to valid range
            pwm = max(1000, min(2000, int(pwm)))
            # Split into 2 bytes (big-endian: high byte first)
            high_byte = (pwm >> 8) & 0xFF
            low_byte = pwm & 0xFF
            packet.extend([high_byte, low_byte])
        
        packet.append(0x55)  # End byte
        
        # Send via SPI (xfer2 returns data, xfer3 is write-only but we use xfer2 for compatibility)
        self.spi.xfer2(packet)
    
    def close(self) -> None:
        """Close the SPI interface."""
        self.spi.close()


class RealGPIO:
    """Real GPIO interface for Linux/Raspberry Pi."""
    
    def __init__(self, sync_pin: int = 17):
        """
        Initialize real GPIO interface.
        
        Args:
            sync_pin: GPIO pin number for sync signal
        """
        from gpiozero import OutputDevice
        import time
        self.sync_pin = OutputDevice(sync_pin)
        self.time = time
        print(f"[GPIO] Sync pin initialized on GPIO {sync_pin} (Physical Pin 11)")
    
    def toggle_sync_pin(self) -> None:
        """Toggle the GPIO sync pin with a 10µs pulse."""
        self.sync_pin.on()
        self.time.sleep(0.00001)  # 10 microsecond pulse
        self.sync_pin.off()


class HardwareInterface:
    """
    Hardware abstraction layer that automatically selects real or mock drivers.
    Detects platform (macOS vs Linux) and instantiates appropriate classes.
    Implements motor-to-Pico mapping for distributed hardware control.
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
        
        # Initialize motor-to-Pico mapping
        self.motor_to_pico_lookup = MOTOR_TO_PICO_LOOKUP
        self.pico_motor_map = PICO_MOTOR_MAP
        
        # Build reverse mapping: pico_id → list of motor_ids
        self.pico_id_to_motors: Dict[int, List[int]] = {}
        for quadrant, config in self.pico_motor_map.items():
            pico_id = config['pico_id']
            if pico_id not in self.pico_id_to_motors:
                self.pico_id_to_motors[pico_id] = []
            self.pico_id_to_motors[pico_id].extend(config['motors'])
        
        # Track pico connection status
        self.pico_connected = {}  # pico_id → bool
        for pico_id in self.pico_id_to_motors.keys():
            self.pico_connected[pico_id] = True  # Assume all connected initially
        
        # SPI interfaces for each Pico (separate chip selects)
        self.spi_interfaces: Dict[int, any] = {}  # pico_id → SPI interface
        
        # Statistics
        self.frames_sent = 0
        self.frames_skipped_motors = []
        
        self._init_drivers()
        self._print_mapping_info()
    
    def _print_mapping_info(self) -> None:
        """Print mapping information at startup."""
        print("\n" + "="*70)
        print("[HW] Motor-to-Pico Mapping Configuration:")
        print("="*70)
        for quadrant, config in self.pico_motor_map.items():
            pico_id = config['pico_id']
            motors = config['motors']
            pin_offset = config['pin_offset']
            desc = config.get('description', '')
            print(f"  {quadrant:<20} → Pico{pico_id} | Motors {motors[0]:2d}-{motors[-1]:2d} | "
                  f"Pins {pin_offset:2d}-{pin_offset + len(motors) - 1:2d} | {desc}")
        print("="*70 + "\n")
    
    def _init_drivers(self) -> None:
        """Initialize SPI and GPIO drivers based on platform."""
        if self.use_mock:
            print(f"[HW] Running on {self.platform} with MOCK drivers")
            # Create one mock SPI per Pico
            for pico_id in self.pico_id_to_motors.keys():
                self.spi_interfaces[pico_id] = MockSPI()
            self.gpio = MockGPIO()
        else:
            print(f"[HW] Running on {self.platform} with REAL drivers")
            try:
                # Create separate SPI interfaces for each Pico
                # Pico 0: SPI bus 0, device 0 (CE0, GPIO 8)
                # Pico 1: SPI bus 0, device 1 (CE1, GPIO 7)
                # Pico 2 & 3: Use GPIO chip selects manually if needed
                for pico_id in sorted(self.pico_id_to_motors.keys()):
                    if pico_id < 2:
                        # Use hardware chip select for Pico 0 and 1
                        self.spi_interfaces[pico_id] = RealSPI(bus=0, device=pico_id)
                        print(f"[HW] Pico{pico_id} initialized on SPI0.{pico_id} (CE{pico_id})")
                    else:
                        # For Pico 2 and 3, you'll need to use GPIO chip selects
                        # This is a limitation - Raspberry Pi only has 2 hardware CE pins
                        print(f"[HW] WARNING: Pico{pico_id} requires manual GPIO chip select (not implemented)")
                        self.spi_interfaces[pico_id] = MockSPI()  # Fallback to mock
                
                self.gpio = RealGPIO()
            except Exception as e:
                print(f"[HW] Failed to init real drivers: {e}, falling back to mock")
                self.use_mock = True
                for pico_id in self.pico_id_to_motors.keys():
                    self.spi_interfaces[pico_id] = MockSPI()
                self.gpio = MockGPIO()
    
    def _map_pwm_values(self, pwm_values: np.ndarray) -> Dict[int, List[int]]:
        """
        Map 36 PWM values to per-Pico lists based on MOTOR_TO_PICO_LOOKUP.
        
        Args:
            pwm_values: numpy array of shape (36,) with PWM values (1000-2000)
        
        Returns:
            Dictionary: pico_id → list of PWM values for that Pico's motors
        """
        pico_pwm_map = {}
        
        for pico_id in self.pico_id_to_motors.keys():
            pico_pwm_map[pico_id] = []
        
        # Map each motor's PWM to its Pico
        for motor_id in range(len(pwm_values)):
            if motor_id not in self.motor_to_pico_lookup:
                # Motor not in mapping - skip silently
                continue
            
            pico_id, pin_on_pico = self.motor_to_pico_lookup[motor_id]
            pwm_value = int(pwm_values[motor_id])
            
            if pico_id not in pico_pwm_map:
                pico_pwm_map[pico_id] = []
            
            # Ensure list is large enough for this pin position
            while len(pico_pwm_map[pico_id]) <= pin_on_pico:
                pico_pwm_map[pico_id].append(1000)  # Default to min PWM
            
            pico_pwm_map[pico_id][pin_on_pico] = pwm_value
        
        return pico_pwm_map
    
    def send_pwm(self, pwm_values: np.ndarray) -> None:
        """
        Send PWM values to motors using motor-to-Pico mapping.
        
        Gracefully handles unmapped or disconnected Picos.
        
        Args:
            pwm_values: numpy array of shape (36,) with PWM values (1000-2000)
        """
        self.frames_sent += 1
        
        # Map PWM values to per-Pico arrays
        pico_pwm_map = self._map_pwm_values(pwm_values)
        
        # Send to each Pico via its dedicated SPI interface
        for pico_id, pwm_list in pico_pwm_map.items():
            if len(pwm_list) == 0:
                continue  # No motors for this Pico
            
            try:
                if self.pico_connected.get(pico_id, False):
                    spi = self.spi_interfaces.get(pico_id)
                    if spi:
                        spi.xfer3(pwm_list)
                        if self.frames_sent % 400 == 0:  # Log every 1 second at 400Hz
                            print(f"[HW] Frame {self.frames_sent}: Pico{pico_id} sent {len(pwm_list)} PWM values")
                else:
                    # Pico disconnected - log once per failure
                    if self.frames_sent == 1:
                        print(f"[HW] Pico{pico_id} marked disconnected - skipping")
            except Exception as e:
                # Graceful failure: mark Pico as disconnected and continue
                if self.pico_connected.get(pico_id, False):
                    print(f"[HW] ERROR: Pico{pico_id} send failed: {e} - marking disconnected")
                    self.pico_connected[pico_id] = False
        
        # Trigger sync pulse (after all Picos have received data)
        try:
            self.gpio.toggle_sync_pin()
        except Exception as e:
            print(f"[HW] ERROR: Sync pin toggle failed: {e}")
    
    def get_connection_status(self) -> Dict[int, bool]:
        """
        Get connection status of all Picos.
        
        Returns:
            Dictionary: pico_id → connected (bool)
        """
        return self.pico_connected.copy()
    
    def close(self) -> None:
        """Close hardware interfaces."""
        for pico_id, spi in self.spi_interfaces.items():
            if hasattr(spi, 'close'):
                try:
                    spi.close()
                    print(f"[HW] Pico{pico_id} SPI interface closed")
                except Exception as e:
                    print(f"[HW] Error closing Pico{pico_id}: {e}")
        print("[HW] Hardware interface closed")
