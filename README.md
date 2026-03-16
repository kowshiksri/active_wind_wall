# Active Wind Wall Control System

A real-time, multi-motor control system for generating dynamic airflow patterns. Controls 36 motors (6×6 grid) via a GUI or programmatic interface with a configurable high-speed control loop, safety constraints, and hardware abstraction for both development and deployment.

## What This System Does

This is a **wind wall experiment platform** that controls 36 independent motors to create time-varying, controllable airflow patterns. Key capabilities:

1. **Motor Grouping** - Organize motors into logical groups (e.g., left half, top quadrant, custom regions)
2. **Signal Generation** - Assign different signal types to groups:
   - Sine waves (customizable frequency, amplitude, phase)
   - Square pulses (for on/off patterns)
   - Constant DC (fixed motor speed)
   - Custom Fourier harmonics (multi-frequency composites)
3. **Real-Time Control** - Deterministic control loop (default 400 Hz, configurable) that:
   - Reconstructs motor signals from pre-computed coefficients
   - Applies safety constraints (slew-rate limiting, PWM bounds checking)
   - Sends PWM commands to hardware controllers
4. **Live Monitoring** - GUI displays real-time motor state, signal graphs, and experiment status
5. **Data Logging** - Records all motor states, timing, and telemetry to CSV for post-experiment analysis
6. **Hardware Abstraction** - Works on macOS (mock hardware for development) or Raspberry Pi 5 (real hardware with 4 Picos)

## How It Works

**Signal Architecture:**
- Pre-computes signal coefficients (using any signal generation method) for each motor group before experiment starts
- During each control loop cycle, reconstructs continuous motor signals from coefficients in real-time
- Each motor gets a PWM duty cycle (1000–2000 µs) based on its current signal value

**Hardware Architecture:**
- **Raspberry Pi 5** (main controller): Runs Python control loop over SPI
- **4× Raspberry Pi Picos** (motor drivers): Each controls 9 motors via PWM
- **Motor Grid Layout**: 6×6 grid divided into 4 quadrants, one per Pico

**Safety & Reliability:**
- Slew-rate limiting prevents motors from changing speed too abruptly (`MAX_PWM_SLEW_LIMIT` µs/ms, absolute — independent of update rate)
- PWM bounds checking ensures commands stay in valid range (1000–2000 µs)
- Two-zone PWM mapping: signal = 0 → 1000 µs (arm/stop); signal > 0 → linear 1200–2000 µs (no dead zone)
- Shared memory buffer for safe IPC between UI and control loop
- Graceful shutdown on Ctrl+C with proper cleanup

## Project Structure

```
active_wind_wall/
├── gui_interface.py                 # Main GUI (PyQt6) - start here for interactive control
├── main.py                          # CLI entry point - launches control loop programmatically
├── requirements.txt                 # Python dependencies (PyQt6, numpy, pandas, etc.)
├── config/
│   └── __init__.py                  # Global config (NUM_MOTORS=36, UPDATE_RATE_HZ=400, etc.)
├── src/
│   ├── core/
│   │   ├── __init__.py
│   │   └── flight_loop.py           # Deterministic control loop (main real-time kernel)
│   ├── hardware/
│   │   ├── __init__.py
│   │   └── interface.py             # Hardware drivers (real SPI for Pi5, mock for macOS)
│   └── physics/
│       ├── __init__.py
│       └── signal_designer.py       # Pre-compute Fourier coefficients (sine, square, etc.)
├── pico/                            # Firmware for Raspberry Pi Picos (C code)
│   ├── firmware_pico0.uf2 → pico3   # Compiled firmware binaries for each Pico
│   └── firmware_template.c          # C template for Pico PWM control
├── tests/
│   ├── plot_log.py                  # Plot logged CSV data
│   ├── test_packet_capture.py       # Validate hardware communication
│   ├── compare_motors.py            # Compare motor response data
│   ├── test_slew_rate.py            # Verify slew limit is rate-independent
│   └── test_pwm_mapping.py          # Verify two-zone PWM mapping and startup seeding
└── logs/                            # Experiment data (CSV format)
```

## Quick Start

### Installation (macOS / Linux Development)

```bash
# Clone or navigate to project directory
cd active_wind_wall

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies (Pi-specific packages are commented out by default)
pip install -r requirements.txt
```

**Note:** `requirements.txt` is configured for development (macOS/Linux). Pi-specific packages (`spidev`, `gpiozero`) are commented out to avoid install failures on non-Pi systems. See the Raspberry Pi section below to enable them for deployment.

### Running the GUI (Recommended for Interactive Control)

```bash
# Launch the graphical interface
python gui_interface.py
```

**In the GUI you can:**
- Create motor groups and assign motors via click
- Configure signal type, frequency, amplitude, and phase per group
- View live motor state graphs
- Monitor control loop performance
- Start/stop experiments with custom duration
- Export experiment data

### Running via Command Line

```bash
# Run with default square wave pattern (10-second duration)
python main.py

# Stop with Ctrl+C (saves logs automatically)
```

### Raspberry Pi 5 (Deployment)

```bash
# Install system dependencies
sudo apt update
sudo apt install python3-pip python3-venv python3-dev

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Enable Pi-specific dependencies
# Edit requirements.txt and uncomment the spidev and gpiozero lines
# Or manually install them:
pip install spidev>=3.5 gpiozero>=2.0.0

# Install remaining dependencies
pip install -r requirements.txt

# Flash Pico firmware (if needed)
# Connect Pico in boot mode and run pico/build_all_firmware.py

# Run the GUI or main.py as above
python gui_interface.py
```

## Usage

### GUI Workflow (Recommended)

1. **Launch:** `python gui_interface.py`
2. **Create Groups:** Click "New Group" to create motor groups (e.g., "Left", "Right", "Top")
3. **Assign Motors:** Click motor buttons in the grid to assign them to the selected group
4. **Configure Signals:** For each group, choose signal type and parameters:
   - **Sine Wave:** Set frequency (Hz), amplitude range (min/max PWM), phase offset (seconds)
   - **Square Pulse:** Configure period and duty cycle
   - **Constant DC:** Set fixed motor speed
   - **Custom Fourier:** Add individual harmonics with amplitude and phase
5. **Run Experiment:** Click "Start Experiment", set duration, and monitor live graphs
6. **Export Data:** CSV logs automatically saved to `logs/` folder with detailed motor states

### Programmatic Workflow (CLI)

Edit [main.py](main.py) to customize experiments:

```python
from src.physics.signal_designer import generate_sine_wave, generate_square_pulse
from src.core.flight_loop import flight_loop
import numpy as np

# Generate custom coefficients
fourier_coeffs = generate_sine_wave(
    n_motors=36,
    amplitude=0.5,
    period=5.0,      # 5-second period
    n_terms=7
)

# Run with custom parameters
main(
    fourier_coeffs=fourier_coeffs,
    experiment_duration_s=30.0,
    enable_logging=True
)
```

### Monitoring & Logging

- **Live Graphs:** GUI shows motor PWM values, signal reconstruction, and control loop timing
- **CSV Logs:** Saved to `logs/packet_capture_YYYYMMDD_HHMMSS.csv`
  - Columns: timestamp, motor_0_pwm, motor_1_pwm, ..., motor_35_pwm
  - Records at log interval (e.g., every 100ms for 400 Hz control loop)
- **Performance Metrics:** GUI displays loop timing jitter and underrun warnings

## Configuration

Key settings are in [config/__init__.py](config/__init__.py):

| Setting | Default | Description |
|---------|---------|-------------|
| `NUM_MOTORS` | 36 | Number of motors in the 6×6 grid |
| `UPDATE_RATE_HZ` | 400 | Control loop frequency (configurable; 2.5 ms per tick at 400 Hz) |
| `PWM_MIN` | 1000 µs | Arm / stopped signal sent to ESC |
| `PWM_MIN_RUNNING` | 1200 µs | Minimum PWM at which motor actually spins (provisional — characterise per motor) |
| `PWM_MAX` | 2000 µs | Full-throttle PWM |
| `MAX_PWM_SLEW_LIMIT` | 25.0 µs/ms | Max PWM rate-of-change in **absolute** terms — does not change when `UPDATE_RATE_HZ` is changed |
| `FOURIER_TERMS` | 7 | Number of Fourier terms for signal reconstruction |
| `BASE_FREQUENCY` | 1.0 Hz | Default base frequency for periodic signals |

## Signal Design

Two signal modes are available, selectable from the **Signal Mode** dropdown at the top of the Signal Configuration panel:

### Mode 1 — Fourier (per group) — default

Signals are pre-computed as Fourier coefficient matrices before the experiment starts, then reconstructed sample-by-sample in real-time during each control loop tick. Each motor group can have an independent signal type:

- **Sine Wave** — smooth oscillation at a configurable frequency and amplitude
- **Square Wave** — on/off pattern synthesised from odd harmonics
- **Constant DC** — fixed motor speed
- **Custom Fourier** — add individual harmonics with amplitude and phase

### Mode 2 — Direct (file)

For experiments where the desired per-motor trajectory is known in advance (e.g., from simulation, CFD data, or a pre-computed optimisation), you can bypass Fourier synthesis entirely and feed the control loop a raw signal table.

**File format:** A 2-D array of shape `[n_frames, n_motors]` with values in `[0, 1]`.

```python
import numpy as np

# Example: 10 seconds at 400 Hz
table = np.zeros((4000, 36))
table[:, 0] = 0.5                  # motor 0 at 50% the whole time
table[1000:3000, 5] = 0.8          # motor 5 at 80% from t=2.5 s to t=7.5 s
np.save("my_signal.npy", table)
```

Load the file via **Browse (.npy / .csv)…** in the GUI. The control loop interpolates linearly between frames and holds the last value when the table is exhausted.

**Accepted formats:** `.npy` (NumPy binary, recommended) or `.csv` (comma-delimited, rows = frames, columns = motors).

## Data Logging & Analysis

Flight data is automatically saved to `logs/packet_capture_YYYYMMDD_HHMMSS.csv` with:
- Timestamp for each measurement
- PWM values (1000–2000 µs) for all 36 motors
- RPM telemetry (when using real hardware)

Log files can be analyzed using the utility scripts in the `tests/` folder:
- `plot_log.py` - Visualize motor behavior over time
- `test_packet_capture.py` - Validate captured data integrity
- `compare_motors.py` - Compare response between motors

## Platform Support

The code automatically detects your platform:

- **macOS**: Development mode with mock hardware (simulates motor control without real devices)
- **Linux/Raspberry Pi**: Production mode with real SPI/GPIO communication via `spidev` and `gpiozero`

No code changes needed—same control loop runs everywhere.

## Hardware Setup (Raspberry Pi 5)

**What You Need:**
- Raspberry Pi 5 (runs main control loop)
- 4× Raspberry Pi Picos (each controls 9 motors)
- 36× DC motors with PWM controllers
- SPI wiring from Pi5 to Picos

**Firmware:**
- Pico firmware (C code) is in the `pico/` folder
- Pre-compiled `.uf2` files are ready to flash
- Build new firmware with: `python pico/build_all_firmware.py`

**Motor Assignment:**
- Motor-to-Pico assignments are fully configurable in `config/__init__.py`
- Default configuration uses the `PICO_MOTOR_MAP` dictionary to define which motors connect to each Pico
- Modify this mapping to match your physical wiring (e.g., if your motors are in a different order or different quadrants)
- See the `PHYSICAL_MOTOR_ORDER` constant for details on byte-level communication with Picos

## Technical Details

For those interested in the implementation:

- **Signal Generation**: Current implementation uses Fourier synthesis (signals pre-computed as coefficient matrices, reconstructed using $\sin(2\pi f t)$), but system is agnostic to generation method
- **Safety Features**: Slew-rate limiting prevents sudden motor speed changes; PWM bounds prevent out-of-range commands
- **Multiprocessing**: Uses Python's `multiprocessing` module with shared memory for efficient IPC between GUI and control loop
- **Hardware Abstraction**: Platform detection (`spidev` vs mock) allows same code to run on development and production systems
- **Deterministic Timing**: Control loop uses busy-spinwait to maintain strict 2.5 ms timing with minimal jitter

## Troubleshooting

| Issue | Solution |
|-------|----------|
| GUI won't launch | Check PyQt6 installation: `pip install --upgrade PyQt6` |
| Motors don't move | Verify Pico firmware is flashed and motors are powered |
| Jerky motor movement | Increase `FOURIER_TERMS` for smoother signals or reduce `MAX_PWM_SLEW_LIMIT` |
| High timing jitter | Close other applications; run with `nice -n -20` on Python process |
| Import errors | Check venv is activated: `source venv/bin/activate` |

## Need Help?

- Check function docstrings—every function has documentation
- Look at log files in `logs/` to see captured experiment data
- Run test scripts in `tests/` to verify signal generation and hardware communication
- Review the configuration in `config/__init__.py` for per-experiment tuning
