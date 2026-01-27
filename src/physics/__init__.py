"""Physics signal generation using Fourier series synthesis."""

import numpy as np
from config import BASE_FREQUENCY, SIGNAL_MIN_DEFAULT, SIGNAL_MAX_DEFAULT


class SignalGenerator:
    """
    Reconstructs motor signals from pre-computed Fourier coefficients.
    Supports optional per-harmonic phase offsets and start-time delay.
    """
    
    def __init__(
        self,
        fourier_coeffs: np.ndarray,
        base_freq: float = BASE_FREQUENCY,
        phase_radians: np.ndarray | None = None,
        start_time_offset: float = 0.0,
        value_min: float = SIGNAL_MIN_DEFAULT,
        value_max: float = SIGNAL_MAX_DEFAULT,
    ):
        """
        Initialize the signal generator with coefficient and optional phase matrices.
        
        Args:
            fourier_coeffs: Coefficient matrix [n_motors, n_terms] (float64)
            base_freq: Base frequency in Hz
            phase_radians: Optional phase offsets [n_motors, n_terms]; defaults to 0
            start_time_offset: Time (s) to delay waveform start (aligns with PWM start)
            value_min: Lower bound for normalized output (no remapping)
            value_max: Upper bound for normalized output (no remapping)
        """
        self.coeffs = fourier_coeffs.astype(np.float64)
        self.n_motors = self.coeffs.shape[0]
        self.n_terms = self.coeffs.shape[1] if len(self.coeffs.shape) > 1 else 1
        self.base_freq = base_freq
        self.omega = 2.0 * np.pi * base_freq
        self.start_time_offset = max(0.0, float(start_time_offset))
        self.value_min = float(value_min)
        self.value_max = float(value_max)
        if self.value_min > self.value_max:
            self.value_min, self.value_max = self.value_max, self.value_min
        if phase_radians is None:
            self.phases = np.zeros_like(self.coeffs)
        else:
            self.phases = np.array(phase_radians, dtype=np.float64)
            if self.phases.shape != self.coeffs.shape:
                raise ValueError("phase_radians must match fourier_coeffs shape")
    
    def get_flow_field(self, t: float) -> np.ndarray:
        """
        Reconstruct signal for all motors at time t using Fourier series.
        
        Formula: Signal_i(t) = A₀ + sum_n(Aₙ * sin(n*ω*(t - t0) + phase[i,n]))
        where coeffs[:, 0] = A₀ (DC offset)
              coeffs[:, 1] = A₁ (1st harmonic)
              coeffs[:, 2] = A₂ (2nd harmonic), etc.
        
        Args:
            t: Time in seconds
        
        Returns:
            Array of shape [n_motors] with values constrained to [value_min, value_max]
        """
        t_eff = max(0.0, t - self.start_time_offset)
        
        # Start with DC offset (coefficient 0)
        signal = self.coeffs[:, 0].copy()
        
        # Add harmonic components (coefficients 1, 2, 3, ...)
        for n in range(1, self.n_terms):
            harmonic_order = n  # n=1 -> 1st harmonic, n=2 -> 2nd harmonic, etc.
            phase = harmonic_order * self.omega * t_eff + self.phases[:, n]
            signal += self.coeffs[:, n] * np.sin(phase)
        
        # Constrain to requested range without remapping full span to [0,1]
        return np.clip(signal, self.value_min, self.value_max)


__all__ = ['SignalGenerator']
