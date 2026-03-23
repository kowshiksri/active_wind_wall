# Active Wind Wall — v1: Deterministic Playback Control

A deterministic motor control platform for a 6×6 fan array (36 motors). Signals are fully pre-computed before an experiment starts and played back at a fixed rate with hardware safety constraints. Runs on Raspberry Pi 5 + Pico (real hardware) or any machine with mock drivers for development.

This is **v1** — the execution and hardware foundation. Signal trajectories are decided before the experiment runs, not during it. Closed-loop and autonomous control are the goals of v2.

---

## What v1 Does

- **Pre-compute signal trajectories** for each motor group before the experiment starts
- **Play back those trajectories** at 400 Hz with deterministic hybrid-sleep timing
- **Enforce safety constraints** on every tick: slew-rate limiting, PWM bounds, motor enable mask
- **Log all motor states** to CSV for post-experiment analysis
- **Write a JSON metadata sidecar** alongside every CSV log — groups, duration, signal mode, start time
- **Save and load experiment presets** — group layout, motor assignments, and signal parameters as JSON
- **Arm and maintain ESCs** via a persistent 20 Hz SPI heartbeat between experiments
- **Provide a GUI** for configuring groups, signals, arming, and monitoring motor state during playback

## What v1 Does Not Do

- No sensor input or feedback of any kind — fully open-loop
- Signal trajectories are fixed at experiment start and cannot be modified mid-run
- No closed-loop or autonomous control (v2)

---

## Signal Modes

Two modes are available, selectable in the GUI before starting an experiment.

### Mode 1 — Fourier (per group)

Motors are organised into groups. Each group is assigned a signal type and parameters. Signals are pre-computed as Fourier coefficient matrices, then reconstructed sample-by-sample during playback.

Available signal types per group:
- **Sine wave** — configurable period, amplitude min/max, phase offset
- **Square wave** — synthesised from odd harmonics (50% duty cycle)
- **Constant DC** — fixed motor speed
- **Custom Fourier** — manually specify individual harmonics, amplitudes, and phases

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

Motors use a two-zone mapping per motor:

| Condition | PWM output | Motor state |
|---|---|---|
| `signal ≤ 0` and `amp_min = 0` | 1000 µs | Armed / stopped |
| `signal > 0` or `amp_min > 0` | `1200 + (amp_min + signal) × 800` µs | Spinning |

**Amplitude floor (`amp_min`):** when a group's minimum amplitude is set above zero, the motor never drops below `1200 + amp_min × 800` µs while running — it maintains a minimum spinning speed rather than stopping at the wave trough. Motors not assigned to any group always receive 1000 µs (armed/idle), regardless of other groups' `amp_min` settings.

**Signal swing:** the Fourier signal is generated to swing from `0` to `(amp_max − amp_min)`. The `amp_min` offset is added at the PWM mapping stage, so the waveform trough always aligns with the minimum running speed and there is no discontinuity.

## Slew Rate Limiting

`MAX_PWM_SLEW_LIMIT` is specified in **µs/ms** — an absolute physical rate, independent of the control loop frequency. Changing `UPDATE_RATE_HZ` does not change the physical motor constraint.

```
per_tick_limit = MAX_PWM_SLEW_LIMIT × LOOP_TIME_MS
```

Default: 25 µs/ms. Square waves bypass the slew limiter to allow instantaneous transitions.

---

## Experiment Presets

Group configurations can be saved to and loaded from JSON files via the GUI.

**What is saved:**
- Signal mode (Fourier / Direct)
- All groups: name, color, motor assignments, signal type, amplitude min/max, period, phase offset, Fourier terms, custom harmonics

**Usage:**
- Click **Save Preset** to export the current configuration to a `.json` file
- Click **Load Preset** to restore a configuration — all groups and motor assignments are rebuilt exactly as saved
- Presets cannot be loaded while an experiment is running

**Preset file format:**
```json
{
  "signal_mode": "Fourier (per group)",
  "groups": [
    {
      "name": "Group 1",
      "color_index": 0,
      "motors": [0, 1, 2, 6, 7, 8],
      "signal_type": "Sine Wave",
      "amp_min": 0.1,
      "amp_max": 0.8,
      "period": 3.0,
      "phase_offset": 0.0,
      "fourier_terms": 7,
      "custom_harmonics": []
    }
  ]
}
```

---

## Experiment Logs

Every experiment produces two files in `logs/`, both sharing the same stem (`YYYYMMDD_HHMMSS`):

| File | Contents |
|---|---|
| `flight_log_<stem>.csv` | Per-motor PWM values at 10 Hz (every 40 frames) |
| `flight_log_<stem>.json` | Metadata sidecar — groups, duration, signal mode, start time |

**Sidecar example:**
```json
{
  "log_stem": "20260323_143000",
  "experiment_start": "2026-03-23T14:30:00.123456",
  "duration_s": 30.0,
  "signal_mode": "Fourier (per group)",
  "groups": [ ... ]
}
```

The sidecar makes every log self-describing — no need to remember what parameters were used for a given run.

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
│   │   └── interface.py             # SPI drivers (real on Pi5, mock on dev)
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
└── logs/                            # CSV + JSON experiment output
```

---

## Quick Start

### Development (Linux / macOS)

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
2. **Load a preset** (optional) — click **Load Preset** to restore a saved group configuration
3. **Create groups** — click "New Group", assign motors from the 6×6 grid
4. **Configure signals** — choose signal mode, set parameters per group (signal type, amplitude min/max, period, phase offset)
5. **Save preset** (optional) — click **Save Preset** to export the current configuration for reuse
6. **Arm motors** — click "Arm Motors"; the system sends a 20 Hz heartbeat to keep ESCs armed
7. **Set duration** and click **Start** to begin playback; monitor live PWM in the oscilloscope panel
8. Logs saved automatically to `logs/flight_log_<stem>.csv` and `logs/flight_log_<stem>.json`
9. Click **Disarm** when finished

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
| `PWM_MIN_RUNNING` | 1200 µs | Minimum spinning speed (provisional — characterise per motor) |
| `PWM_MAX` | 2000 µs | Full throttle |
| `MAX_PWM_SLEW_LIMIT` | 25.0 µs/ms | Absolute slew limit — independent of loop rate |
| `FOURIER_TERMS` | 7 | Default harmonics for Fourier reconstruction |
| `BASE_FREQUENCY` | 1.0 Hz | Default base frequency |

---

## Hardware

- **Raspberry Pi 5** — runs the Python control loop, communicates over SPI
- **4× Raspberry Pi Pico** — each drives 9 motors via PWM; firmware in `pico/`
- **Motor grid** — 6×6, divided into 4 quadrants (one per Pico)

Motor-to-Pico assignments are configured via `PICO_MOTOR_MAP` in `config/__init__.py`. Platform detection is automatic — same code runs in mock mode on any non-Pi machine.

---

## Implementation Notes

- **Timing:** hybrid sleep + 0.5 ms spinlock per frame; sleep yields the CPU to prevent thermal throttling, spinlock ensures sub-millisecond final accuracy. On RPi5 jitter is typically < 0.1 ms.
- **Arming:** a background thread sends 36 × 1000 µs at 20 Hz whenever the system is armed but no experiment is running. The flight loop takes over hardware on experiment start and returns it on stop.
- **Amplitude floor:** `amp_min_per_motor` array passed from GUI to flight loop. Unassigned motors have `amp_min = 0` so they always receive 1000 µs. Assigned motors with `amp_min > 0` never drop below their floor, eliminating the hard PWM discontinuity at the wave trough.
- **IPC:** `multiprocessing.shared_memory` — 288 bytes (PWM array only). Flight loop writes, GUI reads.
- **Startup seeding:** `previous_pwm` is initialised from `signal_gen.get_flow_field(0.0)`, not from `PWM_CENTER`, so there is no forced ramp at experiment start.
- **Duration:** `duration_s` is passed directly into `flight_loop()`. The loop self-terminates when `frame_time ≥ duration_s`, independent of GUI thread timing. The GUI sets `stop_event` as a fallback.
- **Logging:** CSV flushed every ~1 s (400 frames) and on file close. Per-frame flushing was removed as it caused multi-second stalls in the control loop on some systems.
- **Metadata sidecar:** a JSON file is written at experiment start with the full group configuration and parameters, paired to the CSV by a shared log stem. Enables reproducibility without relying on memory or manual notes.
- **Presets:** group configurations are serialised to JSON and can be restored in full — motor assignments, signal types, amplitude bounds, periods, and phase offsets.
- **Hardware abstraction:** `interface.py` encodes PWM → bytes; the flight loop only calls `hardware.send_pwm()` and is protocol-agnostic (PWM today, DShot in future).

---

## Troubleshooting

| Issue | Solution |
|---|---|
| GUI won't launch | `pip install --upgrade PyQt6` |
| Motors don't move | Verify Pico firmware is flashed, motors are powered, and "Arm Motors" was clicked |
| ESCs keep disarming | Confirm heartbeat is running (Arm button should show "Disarm") |
| Jerky motor movement | Reduce `MAX_PWM_SLEW_LIMIT` or increase `FOURIER_TERMS` |
| High timing jitter | Close other applications; `nice -n -20 python gui_interface.py` |
| Log has large time gaps | Ensure no other heavy I/O processes are running; hybrid sleep should prevent this |
| Preset load fails | Ensure preset file was saved by this application; check JSON is not corrupted |
| Import errors | Check venv is active: `source venv/bin/activate` |
