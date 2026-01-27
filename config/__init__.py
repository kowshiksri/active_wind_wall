"""
Global configuration constants for the Active Wind Wall Control System.
"""

# Hardware Configuration
NUM_MOTORS: int = 36
UPDATE_RATE_HZ: int = 400
LOOP_TIME_MS: float = 1000.0 / UPDATE_RATE_HZ  # 2.5 ms

# PWM Signal Configuration
PWM_MIN: int = 1000  # Minimum PWM pulse width in microseconds
PWM_MAX: int = 2000  # Maximum PWM pulse width in microseconds
PWM_CENTER: int = (PWM_MIN + PWM_MAX) // 2  # 1500 µs neutral point

# Safety Parameters
SLEW_LIMIT: int = 50  # Maximum PWM change per loop tick (units/tick)

# Signal Synthesis
FOURIER_TERMS: int = 7  # Number of Fourier coefficients per motor
BASE_FREQUENCY: float = 1.0  # Hz (base frequency for periodic signals)
# Optional per-experiment defaults
EXPERIMENT_DURATION_S: float = 10.0  # Default run length; can be overridden per run
# Normalized signal bounds (can be narrowed per experiment; never remapped)
SIGNAL_MIN_DEFAULT: float = 0.0
SIGNAL_MAX_DEFAULT: float = 1.0

# Visualization Parameters
GUI_UPDATE_RATE_FPS: int = 60
LOG_INTERVAL_MS: int = 100

# Shared Memory
SHARED_MEM_NAME: str = "aww_control_buffer"
SHARED_MEM_SIZE: int = 36 * 8  # 36 motors * PWM values * 8 bytes (float64)
