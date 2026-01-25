# Active Wind Wall Control System v0.1

A high-performance embedded control system for a 36-motor Active Wind Wall using **Python multiprocessing**, **shared memory**, and **real-time signal synthesis**.

## Architecture

### Process A: Flight Control Loop (400 Hz)
- Runs in a dedicated `multiprocessing.Process`
- **Physics Engine:** Fourier-synthesized square wave generation
- **Safety Layer:** Slew-rate limiting and PWM clamping
- **Hardware Interface:** Platform-aware drivers (mock on macOS, real on Linux/RPi)
- **Deterministic Timing:** Spinlock-based loop for exact 2.5 ms tick rate

### Process B: GUI Dashboard (60 FPS)
- PyQt6 + PyqtGraph real-time visualization
- Two scrolling plots: Physics signal and actual PWM commands
- CSV logging at 10 Hz (100 ms intervals)
- Shared memory attachment for zero-copy data access

### Cross-Platform Hardware Abstraction
```
Darwin (macOS)  → MockSPI + MockGPIO (debugging)
Linux (RPi 5)   → Real spidev + lgpio drivers
```

## Project Structure

```
active_wind_wall/
├── main.py                      # Entry point & process orchestration
├── requirements.txt             # Dependencies
├── config/
│   └── settings.py             # Global constants (36 motors, 400 Hz, etc)
├── src/
│   ├── hardware/               # Hardware Abstraction Layer
│   │   └── interface.py        # SPI/GPIO (real vs mock)
│   ├── physics/                # Layer 3: Math & Signal Generation
│   │   └── signal_gen.py       # Fourier synthesis logic
│   ├── core/                   # Layer 2: Control Engine
│   │   ├── shared_mem.py       # Shared memory wrapper
│   │   └── flight_loop.py      # 400 Hz control loop
│   └── gui/                    # Visualization & Logging
│       └── dashboard.py        # PyQt6 dashboard
└── logs/
    └── flight_log_YYYYMMDD_HHMMSS.csv
```

## Configuration

Edit [config/settings.py](config/settings.py):

| Parameter | Value | Notes |
|-----------|-------|-------|
| `NUM_MOTORS` | 36 | 6×6 grid of ESCs |
| `UPDATE_RATE_HZ` | 400 | 2.5 ms per tick |
| `PWM_MIN` / `PWM_MAX` | 1000 / 2000 | µs pulse width |
| `SLEW_LIMIT` | 50 | Safety: max PWM change/tick |
| `HARMONICS` | [1,3,5,7] | Odd harmonics for square wave |
| `BASE_FREQUENCY` | 1.0 | Signal frequency (Hz) |

## Physics Engine

### Fourier Square Wave Synthesis

The signal generator creates a synthetic square wave by summing odd harmonics:

$$\text{Signal}(t) = \sum_{n \in \{1,3,5,7\}} \frac{1}{n} \sin(2\pi \cdot n \cdot f \cdot t)$$

**Properties:**
- Input: time `t` (seconds)
- Output: normalized array of shape (36,) with values ∈ [0.0, 1.0]
- Vectorized computation (numpy, no Python loops)
- Deterministic and repeatable

### Signal-to-PWM Mapping

```python
# Physics output: 0.0 to 1.0
signal = sg.get_flow_field(t)

# Map to PWM range: 1000 to 2000 µs
pwm_target = 1000 + signal * 1000

# Apply safety slew-rate limiting
pwm_delta = np.clip(pwm_target - prev_pwm, -50, +50)
pwm_safe = prev_pwm + pwm_delta

# Final clamp
pwm_final = np.clip(pwm_safe, 1000, 2000)
```

## Installation

### macOS (Development)

```bash
# Install Python 3.8+
python3 --version

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Raspberry Pi 5 (Deployment)

```bash
# Install system dependencies
sudo apt update
sudo apt install python3-pip python3-venv

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies (real hardware drivers included)
pip install -r requirements.txt

# Optional: Install GPIO permissions
sudo usermod -a -G spi,gpio $(whoami)
```

## Usage

### Run on macOS (Mock Hardware)

```bash
cd active_wind_wall
python3 main.py
```

**What you'll see:**
- Flight loop logs at 100-frame intervals (250 ms)
- PyQt6 window opens with real-time plots
- CSV logs created in `logs/` directory
- Hardware detection: "Running on Darwin with MOCK drivers"

### Run on Raspberry Pi (Real Hardware)

```bash
cd active_wind_wall
python3 main.py
```

**Same interface, but now:**
- Actual SPI communication with motor controllers
- GPIO sync pin toggled every 100 frames
- CSV logs identical format for cross-platform analysis

### Stop the System

- **GUI window close button** → Clean shutdown
- **Ctrl+C in terminal** → Signal handler catches SIGINT

**Cleanup:**
- Flight process terminates
- Shared memory unlinked automatically
- CSV logs saved with full data history

## Shared Memory Protocol

Inter-process communication via `multiprocessing.SharedMemory`:

```python
Buffer Shape: (36, 2)  # 36 motors × 2 channels

Column 0: Target PWM values (1000-2000)
Column 1: Telemetry RPM from hardware
```

**Process A (Flight Loop):** Writes PWM + reads RPM telemetry  
**Process B (GUI):** Reads PWM + RPM for visualization  
**Zero-copy performance:** Direct numpy array access

## Logging Format

CSV files in `logs/flight_log_YYYYMMDD_HHMMSS.csv`:

```csv
timestamp,pwm_0,pwm_1,...,pwm_35,rpm_0,rpm_1,...,rpm_35
2026-01-25T14:32:11.123456,1500,1501,1499,...,1502,0,0,...,0
2026-01-25T14:32:11.223456,1502,1501,1500,...,1501,0,0,...,0
...
```

**Logging Rate:** 10 Hz (100 ms intervals)  
**Data Rate:** ~3 KB per log entry  
**Typical Session:** ~100-200 MB for 10 minutes

## Code Quality

✓ **Type Hints:** Every function annotated  
✓ **Docstrings:** Google-style for all classes/methods  
✓ **NumPy Optimization:** Vectorized operations, no Python loops  
✓ **Error Handling:** Graceful fallbacks and informative messages  
✓ **Cross-Platform:** Automatic OS detection and driver selection  

## Debugging

### Enable Verbose Output

Edit [main.py](main.py) and add:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Monitor Shared Memory

In a separate terminal:

```bash
python3 -c "
import sys
sys.path.insert(0, '.')
from src.core import MotorStateBuffer
import numpy as np

buffer = MotorStateBuffer(create=False)
while True:
    pwm = buffer.get_pwm()
    print(f'PWM: min={pwm.min():.0f} max={pwm.max():.0f} mean={pwm.mean():.0f}')
    time.sleep(0.1)
"
```

### Profile CPU Usage

```bash
# macOS
python3 -m cProfile -s cumulative main.py

# Linux
perf record -F 99 python3 main.py
perf report
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError: No module named 'numpy'` | `pip install -r requirements.txt` |
| `AttributeError: 'SharedMemory' object has no attribute 'buffer'` | Requires Python 3.9+ (fixed in v0.1) |
| GUI window doesn't open | Check `DISPLAY` variable on headless systems |
| SPI permission denied (Raspberry Pi) | Run with `sudo` or add user to `spi` group |
| Flight loop stops after a few seconds | Check for exceptions in terminal output |

## Performance Targets

- **Control Loop:** 400 Hz ± 0.5 ms jitter (2.5 ms target)
- **Physics:** <0.1 ms per update (vectorized numpy)
- **GUI:** 60 FPS (PyQt event loop)
- **Memory:** ~50 MB resident (shared memory + GUI buffers)
- **CPU:** Single core at ~80% (spinlock) on RPi 5