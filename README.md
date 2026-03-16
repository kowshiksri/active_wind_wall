# Active Wind Wall — v1: Deterministic Playback Control

A deterministic motor control platform for a 6×6 fan array (36 motors). Signals are fully pre-computed before an experiment starts and played back at a fixed rate with hardware safety constraints. Runs on macOS (mock hardware) or Raspberry Pi 5 + Pico (real hardware).

This is **v1** — the execution and hardware foundation. It is intentionally scope-limited: signal trajectories are decided before the experiment runs, not during it. Closed-loop and autonomous control are the goals of v2.

---

## What v1 Does

- **Pre-compute signal trajectories** for each motor group before the experiment starts
- **Play back those trajectories** at a configurable rate (default 400 Hz) with deterministic timing
- **Enforce safety constraints** on every tick: slew-rate limiting and PWM bounds
- **Log all motor states** to CSV for post-experiment analysis
- **Provide a GUI** for configuring groups, signals, and monitoring motor state during playback

## What v1 Does Not Do

- Motors cannot be changed or overridden while an experiment is running
- There is no sensor input or feedback of any kind
- Signal trajectories are fixed at experiment start — the system is open-loop
- No arming state machine yet (pending firmware work on the Pico side)

---

## Signal Modes

Two modes are available, selectable in the GUI before starting an experiment.

### Mode 1 — Fourier (per group)

Motors are organised into groups. Each group is assigned a signal type and parameters. Signals are pre-computed as Fourier coefficient matrices, then reconstructed sample-by-sample during playback.

Available signal types per group:
- **Sine wave** — frequency (Hz), amplitude, phase offset
- **Square wave** — synthesised from odd harmonics
- **Constant DC** — fixed motor speed
- **Custom Fourier** — manually specify individual harmonics

### Mode 2 — Direct (file)

Supply a pre-computed `[n_frames, n_motors]` array (`.npy` or `.csv`) directly. The control loop interpolates linearly between frames. Useful for arbitrary trajectories from simulation, CFD data, or external optimisation.

**File format:** float64 array with values in `[0, 1]`, rows = time frames, columns = motors.

```python
import numpy as np

# Example: 10 seconds at 400 Hz
table = np.zeros((4000, 36))
table[:, 0] = 0.5                  # motor 0 at 50% throughout
table[1000:3000, 5] = 0.8          # motor 5 at 80% from t=2.5 s to t=7.5 s
np.save("my_signal.npy", table)
```

Signal duration is implicit in the array shape: `duration = n_frames / sample_rate_hz`. When the table is exhausted the last frame value is held.

---

## PWM Mapping

Motors use a two-zone mapping with no dead zone:

| Signal value | PWM output | Motor state |
|---|---|---|
| `0.0` | 1000 µs | Armed / stopped |
| `> 0.0` | 1200 µs → 2000 µs (linear) | Spinning |

Even `signal = 0.01` immediately produces the minimum running speed (1200 µs). There is no range of signal values that maps below the running threshold.

## Slew Rate Limiting

`MAX_PWM_SLEW_LIMIT` is specified in **µs/ms** — an absolute physical rate, independent of the control loop frequency. Changing `UPDATE_RATE_HZ` does not change the physical motor constraint.

```
per_tick_limit = MAX_PWM_SLEW_LIMIT × LOOP_TIME_MS
```

Default: 25 µs/ms (derived from the original 50 DShot units/ms hardware specification).

---

## Project Structure

```
active_wind_wall/
├── gui_interface.py                 # Main GUI (PyQt6)
├── main.py                          # CLI entry point
├── requirements.txt
├── config/
│   └── __init__.py                  # Global constants
├── src/
│   ├── core/
│   │   ├── __init__.py              # MotorStateBuffer (shared memory IPC)
│   │   └── flight_loop.py           # Deterministic playback loop
│   ├── hardware/
│   │   ├── __init__.py
│   │   └── interface.py             # SPI drivers (real on Pi5, mock on macOS)
│   └── physics/
│       ├── __init__.py              # SignalGenerator, DirectSignalGenerator
│       └── signal_designer.py       # Fourier coefficient pre-computation
├── pico/                            # Pico firmware (C)
│   ├── firmware_pico0.uf2 → pico3
│   └── firmware_template.c
├── tests/
│   ├── make_pulse_signal.py         # Generate a test pulse .npy for Direct mode
│   ├── test_slew_rate.py            # Verify slew limit is rate-independent
│   ├── test_pwm_mapping.py          # Verify two-zone mapping and startup seeding
│   ├── plot_log.py                  # Plot logged CSV data
│   ├── test_packet_capture.py       # Validate hardware communication
│   └── compare_motors.py            # Compare motor response across experiments
└── logs/                            # CSV experiment output
```

---

## Quick Start

### Development (macOS / Linux)

```bash
cd active_wind_wall
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python gui_interface.py
```

### Deployment (Raspberry Pi 5)

```bash
sudo apt update && sudo apt install python3-pip python3-venv python3-dev
python3 -m venv venv
source venv/bin/activate

# Uncomment spidev and gpiozero in requirements.txt, then:
pip install -r requirements.txt

python gui_interface.py
```

`requirements.txt` has Pi-specific packages commented out by default to avoid install failures on non-Pi systems.

---

## GUI Workflow

1. `python gui_interface.py`
2. **Create groups** — click "New Group", assign motors from the grid
3. **Configure signals** — choose signal mode, set parameters per group
4. **Start experiment** — set duration, click Start, monitor live PWM graph
5. Logs saved automatically to `logs/flight_log_YYYYMMDD_HHMMSS.csv`

## CLI Workflow

Edit `main.py` directly:

```python
from src.physics.signal_designer import generate_sine_wave
from src.core.flight_loop import flight_loop

fourier_coeffs = generate_sine_wave(n_motors=36, amplitude=0.5, period=5.0, n_terms=7)
main(fourier_coeffs=fourier_coeffs, experiment_duration_s=30.0, enable_logging=True)
```

## Testing Direct Mode

```bash
# Generate a 5-second pulse signal and open the GUI with instructions
python tests/make_pulse_signal.py --launch-gui
```

---

## Configuration

All constants in `config/__init__.py`:

| Setting | Default | Description |
|---|---|---|
| `NUM_MOTORS` | 36 | Motors in the 6×6 grid |
| `UPDATE_RATE_HZ` | 400 | Playback loop frequency |
| `PWM_MIN` | 1000 µs | Arm / stopped |
| `PWM_MIN_RUNNING` | 1200 µs | Minimum spinning speed (characterise per motor) |
| `PWM_MAX` | 2000 µs | Full throttle |
| `MAX_PWM_SLEW_LIMIT` | 25.0 µs/ms | Absolute slew limit — independent of loop rate |
| `FOURIER_TERMS` | 7 | Harmonics for Fourier reconstruction |
| `BASE_FREQUENCY` | 1.0 Hz | Default base frequency |

---

## Hardware

- **Raspberry Pi 5** — runs the Python control loop, communicates over SPI
- **4× Raspberry Pi Pico** — each drives 9 motors via PWM; firmware in `pico/`
- **Motor grid** — 6×6, divided into 4 quadrants (one per Pico)

Motor-to-Pico assignments are configured via `PICO_MOTOR_MAP` in `config/__init__.py`. Platform detection is automatic — same code runs on macOS (mock) and Pi (real SPI).

---

## Implementation Notes

- **Timing**: busy-spinwait loop for deterministic 2.5 ms ticks; jitter on RPi5 typically < 0.1 ms
- **IPC**: `multiprocessing.shared_memory` for one-directional state passing from flight loop to GUI monitor
- **Startup seeding**: `previous_pwm` is initialised from `signal_gen.get_flow_field(0.0)`, not from `PWM_CENTER`, so there is no forced ramp at experiment start
- **Hardware abstraction**: `interface.py` encodes PWM → bytes; the flight loop only calls `hardware.send_pwm()` and is protocol-agnostic (PWM today, DShot in future)

---

## Troubleshooting

| Issue | Solution |
|---|---|
| GUI won't launch | `pip install --upgrade PyQt6` |
| Motors don't move | Verify Pico firmware is flashed and motors are powered |
| Jerky motor movement | Reduce `MAX_PWM_SLEW_LIMIT` or increase `FOURIER_TERMS` |
| High timing jitter | Close other applications; `nice -n -20 python gui_interface.py` |
| Import errors | Check venv is active: `source venv/bin/activate` |
