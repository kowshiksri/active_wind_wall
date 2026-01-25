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
HARMONICS: list = [1, 3, 5, 7]  # Odd harmonics for square wave synthesis
BASE_FREQUENCY: float = 1.0  # Hz (can be modulated)

# Visualization Parameters
GUI_UPDATE_RATE_FPS: int = 60
LOG_INTERVAL_MS: int = 100

# Shared Memory
SHARED_MEM_NAME: str = "aww_control_buffer"
SHARED_MEM_SIZE: int = 36 * 2 * 8  # 36 motors * 2 channels (PWM, RPM) * 8 bytes (float64)
