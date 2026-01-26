"""Physics signal generation using Fourier series synthesis."""

import numpy as np
from config import NUM_MOTORS, BASE_FREQUENCY, FOURIER_TERMS


class SignalGenerator:
    """
    Reconstructs motor signals from pre-computed Fourier coefficients.
    Each motor can have independent waveforms via separate coefficient rows.
    """
    
    def __init__(self, fourier_coeffs: np.ndarray, base_freq: float = BASE_FREQUENCY):
        """
        Initialize the signal generator with coefficient matrix.
        
        Args:
            fourier_coeffs: Coefficient matrix [n_motors, n_terms] (float64)
            base_freq: Base frequency in Hz
        """
        self.coeffs = fourier_coeffs.astype(np.float64)
        self.n_motors = self.coeffs.shape[0]
        self.n_terms = self.coeffs.shape[1] if len(self.coeffs.shape) > 1 else 1
        self.base_freq = base_freq
        self.omega = 2.0 * np.pi * base_freq
    
    def get_flow_field(self, t: float) -> np.ndarray:
        """
        Reconstruct signal for all motors at time t using Fourier series.
        
        Formula: Signal_i(t) = sum_n(coeff[i,n] * cos((n+1)*ω*t))
        
        Args:
            t: Time in seconds
        
        Returns:
            Array of shape [n_motors] with normalized values in [0.0, 1.0]
        """
        signal = np.zeros(self.n_motors, dtype=np.float64)
        
        # Reconstruct signal from coefficients
        for n in range(self.n_terms):
            harmonic_order = n + 1
            phase = harmonic_order * self.omega * t
            signal += self.coeffs[:, n] * np.cos(phase)
        
        # Normalize to [0, 1]
        signal = np.clip(signal, 0.0, 1.0)
        return signal


__all__ = ['SignalGenerator']
