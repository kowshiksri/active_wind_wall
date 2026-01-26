"""
Hardware Abstraction Layer for cross-platform compatibility.
Detects OS and provides real or mock hardware interfaces.
"""

import platform
from typing import List, Optional
import numpy as np


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
        import spidev
        self.spi = spidev.SpiDev()
        self.spi.open(bus, device)
        self.spi.max_speed_hz = 1000000  # 1 MHz
    
    def xfer3(self, pwm_values: List[int]) -> None:
        """
        Transfer PWM values via SPI (one-way, PWM only).
        
        Args:
            pwm_values: List of 36 PWM values
        """
        # Convert PWM values to bytes and transfer
        self.spi.xfer3(pwm_values)
    
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
        import lgpio
        self.gpio = lgpio.gpiochip_open(0)
        self.sync_pin = sync_pin
        lgpio.gpio_claim_output(self.gpio, self.sync_pin)
    
    def toggle_sync_pin(self) -> None:
        """Toggle the GPIO sync pin."""
        import lgpio
        lgpio.gpio_write(self.gpio, self.sync_pin, 1)
        lgpio.gpio_write(self.gpio, self.sync_pin, 0)


class HardwareInterface:
    """
    Hardware abstraction layer that automatically selects real or mock drivers.
    Detects platform (macOS vs Linux) and instantiates appropriate classes.
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
        
        self._init_drivers()
    
    def _init_drivers(self) -> None:
        """Initialize SPI and GPIO drivers based on platform."""
        if self.use_mock:
            print(f"[HW] Running on {self.platform} with MOCK drivers")
            self.spi = MockSPI()
            self.gpio = MockGPIO()
        else:
            print(f"[HW] Running on {self.platform} with REAL drivers")
            try:
                self.spi = RealSPI()
                self.gpio = RealGPIO()
            except Exception as e:
                print(f"[HW] Failed to init real drivers: {e}, falling back to mock")
                self.use_mock = True
                self.spi = MockSPI()
                self.gpio = MockGPIO()
    
    def send_pwm(self, pwm_values: np.ndarray) -> None:
        """
        Send PWM values to motors (one-way, PWM only).
        
        Args:
            pwm_values: numpy array of shape (36,) with PWM values (1000-2000)
        """
        # Convert to list and send via SPI
        pwm_list = pwm_values.astype(int).tolist()
        self.spi.xfer3(pwm_list)
        
        # Toggle sync pin
        self.gpio.toggle_sync_pin()
    
    def close(self) -> None:
        """Close hardware interfaces."""
        if hasattr(self.spi, 'close'):
            self.spi.close()
        print("[HW] Hardware interface closed")
