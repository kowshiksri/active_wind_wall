"""
Signal design module for pre-computing Fourier coefficients.
Generates coefficient matrices before flight loop starts.
"""

import numpy as np
from config import NUM_MOTORS, FOURIER_TERMS, BASE_FREQUENCY


def generate_square_pulse(
    n_motors: int = NUM_MOTORS,
    amplitude: float = 1.0,
    period: float = 10.0,
    duty_cycle: float = 0.5,
    n_terms: int = FOURIER_TERMS,
    base_freq: float = BASE_FREQUENCY
) -> np.ndarray:
    """
    Generate Fourier coefficients for a square wave pulse.
    
    Fourier series: signal(t) = A₀ + Σ Aₙ * sin(n*2π*f*t)
    For square wave: A₀ = amplitude * duty_cycle
                     Aₙ = (2*amplitude/nπ) * sin(n*π*duty_cycle)
    
    Args:
        n_motors: Number of motors (all get same coefficients)
        amplitude: Signal amplitude in [0, 1]
        period: Period in seconds
        duty_cycle: Fraction of period that is "on" (0.5 = 50%)
        n_terms: Number of Fourier terms
        base_freq: Base frequency in Hz (1/period)
    
    Returns:
        Coefficient matrix [n_motors, n_terms]
        coeffs[:, 0] = DC offset
        coeffs[:, 1] = 1st harmonic amplitude
        coeffs[:, 2] = 2nd harmonic amplitude, etc.
    """
    coeffs = np.zeros((n_motors, n_terms))
    
    # DC component (average value)
    dc_offset = amplitude * duty_cycle
    coeffs[:, 0] = dc_offset
    
    # Harmonic components (n=1, 2, 3, ...)
    for n in range(1, n_terms):
        harmonic_order = n
        # Fourier coefficient for square wave
        sin_term = np.sin(harmonic_order * np.pi * duty_cycle)
        a_n = (2.0 * amplitude / (harmonic_order * np.pi)) * sin_term
        coeffs[:, n] = a_n
    
    return coeffs


def generate_uniform(
    n_motors: int = NUM_MOTORS,
    value: float = 0.5,
    n_terms: int = FOURIER_TERMS
) -> np.ndarray:
    """
    Generate coefficients for constant signal (DC).
    All motors output same constant value.
    
    Args:
        n_motors: Number of motors
        value: Constant output in [0, 1]
        n_terms: Number of Fourier terms (only first matters)
    
    Returns:
        Coefficient matrix [n_motors, n_terms]
    """
    coeffs = np.zeros((n_motors, n_terms))
    coeffs[:, 0] = value  # DC component
    return coeffs


def generate_sine_wave(
    n_motors: int = NUM_MOTORS,
    amplitude: float = 1.0,
    period: float = 1.0,
    dc_offset: float = 0.5,
    n_terms: int = FOURIER_TERMS,
    base_freq: float = BASE_FREQUENCY
) -> np.ndarray:
    """
    Generate Fourier coefficients for a sine wave.
    For a sine wave, only the fundamental frequency has non-zero coefficient.
    
    signal(t) = dc_offset + amplitude * sin(2π*t/period)
    
    Args:
        n_motors: Number of motors (all get same coefficients)
        amplitude: Amplitude around DC offset (0 to 0.5 typical)
        period: Period in seconds
        dc_offset: Vertical offset (0.5 keeps signal in [0, 1])
        n_terms: Number of Fourier terms (only first 2 matter for sine)
        base_freq: Base frequency in Hz (1/period)
    
    Returns:
        Coefficient matrix [n_motors, n_terms]
    """
    coeffs = np.zeros((n_motors, n_terms))
    
    # For a sine wave decomposition:
    # Harmonic 0 (DC): dc_offset
    # Harmonic 1 (fundamental): amplitude (for sine basis)
    # All higher harmonics: 0
    
    # Store DC offset in first column
    coeffs[:, 0] = dc_offset
    
    # Store fundamental sine amplitude in second column (if space available)
    if n_terms > 1:
        coeffs[:, 1] = amplitude
    
    return coeffs


def generate_custom(
    coefficients: np.ndarray
) -> np.ndarray:
    """
    Accept pre-computed coefficient matrix directly.
    
    Args:
        coefficients: [n_motors, n_terms] array
    
    Returns:
        Same coefficient matrix
    """
    return coefficients.astype(np.float64)


__all__ = ['generate_square_pulse', 'generate_uniform', 'generate_sine_wave', 'generate_custom']
