"""
Global configuration constants for the Active Wind Wall Control System.

All tunable parameters live here. See config/PARAMETERS.md for the full
derivation and rationale behind every value — read that before changing
anything, especially UPDATE_RATE_HZ, SPI_SPEED_HZ, or the PWM limits.
"""

# ─────────────────────────────────────────────
# HARDWARE TOPOLOGY
# ─────────────────────────────────────────────
NUM_MOTORS: int = 36          # Total motors in the array (6×6 grid)
NUM_PICOS:  int = 4           # Number of Pico boards
MOTORS_PER_PICO: int = NUM_MOTORS // NUM_PICOS   # Derived — do not set manually

# ─────────────────────────────────────────────
# CONTROL LOOP TIMING
# ─────────────────────────────────────────────
# UPDATE_RATE_HZ is constrained by SPI frame delivery time, not by the Pico.
# See config/PARAMETERS.md §"Loop Rate Derivation" for the full calculation.
#
# With 1 MHz SPI and Python byte-at-a-time overhead (~150 µs/byte worst case):
#   frame delivery = 36 bytes × 158 µs = 5,688 µs
#   + 200 µs inter-frame buffer          = 5,888 µs  →  ~170 Hz max
#   × 1.15 safety margin                 = ~6,770 µs →  ~147 Hz
#   rounded to clean number              = 125 Hz (8 ms loop)
#
# ESCs update their own PWM output at 50 Hz — 125 Hz is already 2.5× that.
# Do NOT raise this above 170 without first switching to a single xfer2() SPI call.
UPDATE_RATE_HZ: int   = 125
LOOP_TIME_MS:  float  = 1000.0 / UPDATE_RATE_HZ   # 8.0 ms — derived, do not edit

# ─────────────────────────────────────────────
# PWM SIGNAL RANGE
# ─────────────────────────────────────────────
# Standard RC/ESC servo PWM: 1000 µs = stopped/armed, 2000 µs = full throttle.
# These values must match the Pico firmware (firmware_template.c) exactly.
# If you change PWM_MIN_RUNNING here, update the Pico firmware mapping too.
PWM_MIN:         int = 1000   # µs — armed/idle (ESC holds but does not spin)
PWM_MIN_RUNNING: int = 1000   # µs — minimum pulse to actually spin the motor
                               #      provisional: characterise per motor type
PWM_MAX:         int = 2000   # µs — full throttle
PWM_CENTER:      int = (PWM_MIN + PWM_MAX) // 2   # 1500 µs — midpoint, derived

# ─────────────────────────────────────────────
# SAFETY CONSTRAINTS
# ─────────────────────────────────────────────
# Slew limit is in µs/ms — absolute, loop-rate-independent.
# 25 µs/ms means a motor can travel the full 800 µs PWM range in ~32 ms.
# Raise this if motors feel sluggish; lower it if startup jerks are a problem.
MAX_PWM_SLEW_LIMIT: float = 25.0   # µs/ms

# ─────────────────────────────────────────────
# SIGNAL SYNTHESIS
# ─────────────────────────────────────────────
FOURIER_TERMS:        int   = 7     # Harmonics per motor for Fourier synthesis
BASE_FREQUENCY:       float = 1.0   # Hz — fundamental frequency for periodic signals
EXPERIMENT_DURATION_S: float = 10.0 # Default run length in seconds (overridable per run)
SIGNAL_MIN_DEFAULT:   float = 0.0   # Normalized signal lower bound
SIGNAL_MAX_DEFAULT:   float = 1.0   # Normalized signal upper bound

# ─────────────────────────────────────────────
# GUI / LOGGING
# ─────────────────────────────────────────────
GUI_UPDATE_RATE_FPS: int = 40       # GUI oscilloscope refresh rate (Hz)
LOG_INTERVAL_MS:     int = 100      # CSV log entry interval (ms)

# ─────────────────────────────────────────────
# SHARED MEMORY (inter-process, GUI ↔ flight loop)
# ─────────────────────────────────────────────
SHARED_MEM_NAME: str = "aww_control_buffer"
SHARED_MEM_SIZE: int = NUM_MOTORS * 8   # NUM_MOTORS × float64 (8 bytes each) — derived

# ─────────────────────────────────────────────
# SPI BUS CONFIGURATION
# ─────────────────────────────────────────────
# The Pico is SPI slave — it accepts whatever clock the Pi master drives.
# SPI_SPEED_HZ sets the Pi master clock via spidev.max_speed_hz.
#
# Timing budget at 1 MHz with Python byte-at-a-time overhead:
#   pure SPI/byte = 8 µs  |  Python overhead/byte ≈ 150 µs worst case
#   See config/PARAMETERS.md §"SPI Clock Choice" for full analysis.
SPI_BUS:      int = 0          # spidev bus number  (SPI0 on Pi)
SPI_DEVICE:   int = 0          # spidev device number (CE0)
SPI_SPEED_HZ: int = 1_000_000  # 1 MHz — Pi drives this; Pico slave ignores its own spi_init() baud

# ─────────────────────────────────────────────
# GPIO SYNC PIN (Pi side)
# ─────────────────────────────────────────────
# Rising edge on this pin tells all Picos to latch the SPI frame and update PWM.
# NOTE: interface.py currently hardcodes GPIO 22 — this constant must match that.
SYNC_PIN:            int = 22   # GPIO BCM number on Pi (was wrongly 17 — corrected)
SYNC_PULSE_WIDTH_US: int = 10   # Pulse high duration in µs

# ─────────────────────────────────────────────
# PICO HARDWARE MAPPING
# ─────────────────────────────────────────────
# Maps logical motor IDs (0–35) to physical Pico boards and pin positions.
# Edit FULL_PICO_MOTOR_MAP to match your actual wiring.
# Set SINGLE_MOTOR_TEST = True to test one motor on Pico0 without running all boards.
#
# Default physical layout:
#   Motors  0– 8  →  Pico 0  (top-left  3×3)
#   Motors  9–17  →  Pico 1  (top-right 3×3)
#   Motors 18–26  →  Pico 2  (bottom-left  3×3)
#   Motors 27–35  →  Pico 3  (bottom-right 3×3)

SINGLE_MOTOR_TEST: bool = False

FULL_PICO_MOTOR_MAP: dict = {
    'quadrant_top_left': {
        'pico_id': 0,
        'motors': list(range(0, 9)),
        'pin_offset': 0,
        'description': 'Top-Left 3x3 Grid'
    },
    'quadrant_top_right': {
        'pico_id': 1,
        'motors': list(range(9, 18)),
        'pin_offset': 0,
        'description': 'Top-Right 3x3 Grid'
    },
    'quadrant_bottom_left': {
        'pico_id': 2,
        'motors': list(range(18, 27)),
        'pin_offset': 0,
        'description': 'Bottom-Left 3x3 Grid'
    },
    'quadrant_bottom_right': {
        'pico_id': 3,
        'motors': list(range(27, 36)),
        'pin_offset': 0,
        'description': 'Bottom-Right 3x3 Grid'
    }
}

PICO_MOTOR_MAP: dict = (
    {
        'single_motor_test': {
            'pico_id': 0,
            'motors': [0],
            'pin_offset': 0,
            'description': 'Single Motor Test (Motor 0 on Pico0)'
        }
    }
    if SINGLE_MOTOR_TEST
    else FULL_PICO_MOTOR_MAP
)

# Derived reverse lookup: motor_id → (pico_id, pin_on_pico)
# Auto-built from PICO_MOTOR_MAP — do not edit directly.
def _build_motor_pico_lookup() -> dict:
    lookup = {}
    for _, cfg in PICO_MOTOR_MAP.items():
        for pin_index, motor_id in enumerate(cfg['motors']):
            lookup[motor_id] = (cfg['pico_id'], cfg['pin_offset'] + pin_index)
    return lookup

MOTOR_TO_PICO_LOOKUP: dict = _build_motor_pico_lookup()
