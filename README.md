# Active Wind Wall Control System

A real-time control system for a 36-motor Active Wind Wall that generates time-varying flow patterns using Fourier-based signal synthesis.

## What This Code Does

This system controls 36 motors (arranged in a 6×6 grid) to create precise airflow patterns. It:

1. **Generates Signals** - Creates motor control signals using Fourier series (sine waves, square pulses, etc.)
2. **Runs Control Loop** - Executes a high-speed loop at 400 Hz (every 2.5 ms) to update all motors
3. **Ensures Safety** - Applies limits on how fast motors can change speed (slew-rate limiting)
4. **Sends Commands** - Communicates with motor controllers using PWM signals (1000-2000 microseconds)
5. **Logs Data** - Records all motor states to CSV files for analysis

## How It Works

The system uses **Fourier coefficients** to pre-compute signal patterns. During operation:
- The `flight_loop` reconstructs motor signals in real-time from these coefficients
- Each motor receives PWM commands that are safely limited and validated
- Hardware abstraction allows the code to run on macOS (for testing) or Linux (for real hardware)

## Project Structure

```
active_wind_wall/
├── main.py                          # Start here - launches the control loop
├── requirements.txt                 # Python dependencies
├── config/                          # Configuration settings
│   └── __init__.py                 # Motor count, frequencies, PWM limits
├── src/
│   ├── core/
│   │   └── flight_loop.py          # Main control loop (400 Hz)
│   ├── hardware/
│   │   └── interface.py            # Hardware drivers (real or mock)
│   └── physics/
│       └── signal_designer.py      # Pre-compute Fourier coefficients
└── logs/                            # Recorded flight data (CSV)
```

## Quick Start

### Installation

```bash
# Clone or download this repository
cd active_wind_wall

# Install dependencies
pip install -r requirements.txt
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

### Run the System

```bash
python main.py
```

The system will:
- Generate default square wave pattern (10-second period)
- Launch the control loop running at 400 Hz
- Create CSV log files in the `logs/` folder
- Automatically detect your platform (macOS uses mock hardware, Linux uses real hardware)

### Stop the System

Press `Ctrl+C` to stop the program. It will shut down gracefully and save all log data.

## Configuration

Key settings are in [config/__init__.py](config/__init__.py):

| Setting | Default | Description |
|---------|---------|-------------|
| `NUM_MOTORS` | 36 | Number of motors in the grid |
| `UPDATE_RATE_HZ` | 400 | Control loop frequency (400 Hz = 2.5 ms) |
| `PWM_MIN` / `PWM_MAX` | 1000 / 2000 | PWM pulse width range (microseconds) |
| `SLEW_LIMIT` | 50 | Max PWM change per update (safety feature) |
| `FOURIER_TERMS` | 20 | Number of Fourier terms for signal reconstruction |

## Signal Design

The system uses Fourier series to generate smooth, repeatable motor patterns. You can create different signal types in [src/physics/signal_designer.py](src/physics/signal_designer.py):

- **Square Pulse** - On/off pattern (default)
- **Sine Wave** - Smooth oscillation
- **Uniform** - Constant speed for all motors

Each signal is pre-computed as Fourier coefficients, then reconstructed in real-time during the control loop.

## Data Logging

Flight data is automatically saved to `logs/flight_log_YYYYMMDD_HHMMSS.csv` with:
- Timestamp for each update
- PWM values for all 36 motors
- RPM telemetry (when using real hardware)

Log files can be analyzed using the test notebooks in the `tests/` folder.

## Platform Support

- **macOS**: Development mode with mock hardware (prints to console, no actual motor control)
- **Linux/Raspberry Pi**: Production mode with real SPI/GPIO communication to motor controllers

The code automatically detects which platform you're running on.

## Need Help?

- Check the code comments - every function has documentation
- Look at log files in the `logs/` folder to see what the system is doing
- Run tests in the `tests/` folder to verify signal generation

## Technical Details

For those interested in the implementation:

- **Fourier Synthesis**: Signals are pre-computed as coefficient matrices and reconstructed using `sin(2πft)` during flight
- **Safety Features**: Slew-rate limiting prevents sudden motor speed changes
- **Multiprocessing**: Uses Python's `multiprocessing` module with shared memory for efficient data sharing
- **Hardware Abstraction**: Platform detection allows the same code to run on development machines and real hardware
