"""Physics signal generation using Fourier series synthesis."""

import numpy as np
from config import HARMONICS, BASE_FREQUENCY, NUM_MOTORS


class SignalGenerator:
    """
    Generates PWM control signals using Fourier series synthesis.
    Produces a square wave by summing odd harmonics.
    """
    
    def __init__(self, frequency: float = BASE_FREQUENCY):
        """
        Initialize the signal generator.
        
        Args:
            frequency: Base frequency in Hz for the generated signal
        """
        self.frequency = frequency
        self.harmonics = np.array(HARMONICS, dtype=np.float64)
        # Precompute harmonic coefficients: 1/n for each harmonic
        self.coefficients = 1.0 / self.harmonics
    
    def get_flow_field(self, t: float) -> np.ndarray:
        """
        Generate a square wave signal using Fourier synthesis.
        
        Formula: Signal(t) = sum(1/n * sin(2π * n * f * t)) for n in HARMONICS
        
        Args:
            t: Time in seconds
        
        Returns:
            Normalized numpy array of shape (36,) with values in [0.0, 1.0]
            Represents the requested signal level for all 36 motors
        """
        # Create phase array for all harmonics at time t
        phases = 2.0 * np.pi * self.harmonics * self.frequency * t
        
        # Compute sine of all phases
        sines = np.sin(phases)
        
        # Apply coefficients (1/n) and sum: scalar
        signal_value = np.sum(self.coefficients * sines)
        
        # Normalize to [0.0, 1.0] range
        max_value = np.sum(self.coefficients)  # ~1.533
        normalized = (signal_value / max_value + 1.0) / 2.0
        normalized = np.clip(normalized, 0.0, 1.0)
        
        # Broadcast to all 36 motors (all get the same signal)
        return np.full(NUM_MOTORS, normalized, dtype=np.float64)
    
    def set_frequency(self, frequency: float) -> None:
        """
        Update the signal generation frequency.
        
        Args:
            frequency: New frequency in Hz
        """
        self.frequency = frequency


__all__ = ['SignalGenerator']
