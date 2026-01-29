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

# Pico Hardware Mapping
# Maps motors to Picos and their pin positions on each Pico.
# Modify this mapping to change which motors connect to which Picos.
# Structure:
#   - 'pico_id': Which Pico receives these motors (0-3 for 4 Picos)
#   - 'motors': List of motor IDs for this Pico
#   - 'pin_offset': Starting pin position on this Pico (for future use with varied pin layouts)
#
# PHYSICAL LAYOUT (default):
#   Motors 0-8:    Top-Left Quadrant    → Pico0
#   Motors 9-17:   Top-Right Quadrant   → Pico1
#   Motors 18-26:  Bottom-Left Quadrant → Pico2
#   Motors 27-35:  Bottom-Right Quadrant → Pico3
#
# CHANGE THIS MAPPING TO:
#   - Swap which Pico connects to which quadrant
#   - Change pin order within a Pico
#   - Redistribute motors across Picos
#   - Test with single Pico (motors map to Pico0, others are ignored)

PICO_MOTOR_MAP: dict = {
    'quadrant_top_left': {
        'pico_id': 0,
        'motors': list(range(0, 9)),      # Motors 0-8
        'pin_offset': 0,                  # Pins 0-8 on Pico0
        'description': 'Top-Left 3x3 Grid'
    },
    'quadrant_top_right': {
        'pico_id': 1,
        'motors': list(range(9, 18)),     # Motors 9-17
        'pin_offset': 0,                  # Pins 0-8 on Pico1
        'description': 'Top-Right 3x3 Grid'
    },
    'quadrant_bottom_left': {
        'pico_id': 2,
        'motors': list(range(18, 27)),    # Motors 18-26
        'pin_offset': 0,                  # Pins 0-8 on Pico2
        'description': 'Bottom-Left 3x3 Grid'
    },
    'quadrant_bottom_right': {
        'pico_id': 3,
        'motors': list(range(27, 36)),    # Motors 27-35
        'pin_offset': 0,                  # Pins 0-8 on Pico3
        'description': 'Bottom-Right 3x3 Grid'
    }
}

# Derived motor-to-Pico lookup (auto-generated from PICO_MOTOR_MAP)
# Maps motor_id → (pico_id, pin_position_on_pico)
def _build_motor_pico_lookup() -> dict:
    """Build reverse lookup: motor_id → (pico_id, pin_on_pico)"""
    lookup = {}
    for quadrant_name, config in PICO_MOTOR_MAP.items():
        pico_id = config['pico_id']
        pin_offset = config['pin_offset']
        for pin_index, motor_id in enumerate(config['motors']):
            pin_on_pico = pin_offset + pin_index
            lookup[motor_id] = (pico_id, pin_on_pico)
    return lookup

MOTOR_TO_PICO_LOOKUP: dict = _build_motor_pico_lookup()

# SPI Configuration
SPI_BUS: int = 0           # SPI bus number (0 for default)
SPI_DEVICE: int = 0        # SPI device number (0 for default)
SPI_SPEED_HZ: int = 1000000  # 1 MHz SPI speed

# GPIO Sync Pin Configuration
SYNC_PIN: int = 17         # GPIO pin for synchronization trigger
SYNC_PULSE_WIDTH_US: int = 10  # Sync pulse width in microseconds
