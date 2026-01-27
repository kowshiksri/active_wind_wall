"""
High-speed flight control loop (Process A).
Runs at 400 Hz with deterministic timing and safety checks.
"""

import time
import csv
from pathlib import Path
from datetime import datetime
import numpy as np
from multiprocessing import Event
from config import (
    NUM_MOTORS, UPDATE_RATE_HZ, PWM_MIN, PWM_MAX, PWM_CENTER,
    SLEW_LIMIT, LOOP_TIME_MS, BASE_FREQUENCY,
    SIGNAL_MIN_DEFAULT, SIGNAL_MAX_DEFAULT
)
from src.hardware import HardwareInterface
from src.physics import SignalGenerator
from src.core import MotorStateBuffer


def flight_loop(
    stop_event: Event, # type: ignore
    use_mock_hardware: bool = True,
    fourier_coeffs: np.ndarray | None = None,
    base_freq: float | None = None,
    omega_per_motor: np.ndarray | None = None,
    phase_radians: np.ndarray | None = None,
    start_time_offset: float = 0.0,
    value_min: float | None = None,
    value_max: float | None = None,
    enable_logging: bool = True,
    log_interval_frames: int = 40,
    slew_limit_override: float | None = None,
) -> None: # type: ignore
    """
    Main flight control loop running at 400 Hz.
    
    This function runs in a separate Process and:
    1. Reconstructs motor signals from Fourier coefficients
    2. Applies safety constraints (slew rate limiting, PWM clamping)
    3. Sends commands to hardware via SPI
    4. Reads telemetry from hardware
    5. Updates shared memory for the GUI
    6. Maintains deterministic 2.5 ms loop timing
    
    Args:
        stop_event: multiprocessing.Event to signal loop termination
        use_mock_hardware: If True, use mock drivers; if False, use real drivers
        fourier_coeffs: Coefficient matrix [n_motors, n_terms] for signal generation
        base_freq: Base frequency for signal generation
        phase_radians: Phase offset for each motor
        start_time_offset: Time offset to start signal generation
        value_min: Minimum signal value
        value_max: Maximum signal value
        enable_logging: If True, log data to CSV file
        log_interval_frames: Log every N frames (default 40 = 100ms at 400Hz)
    """
    print(f"[FlightLoop] Initializing at {UPDATE_RATE_HZ} Hz ({LOOP_TIME_MS:.2f} ms)")
    
    try:
        # Initialize hardware interface with platform detection
        hardware = HardwareInterface(use_mock=use_mock_hardware)
        
        # Initialize physics engine with coefficient matrix and timing/phase options
        if fourier_coeffs is None:
            raise ValueError("fourier_coeffs must be provided to flight_loop")
        signal_gen = SignalGenerator(
            fourier_coeffs,
            base_freq=base_freq if base_freq is not None else BASE_FREQUENCY,
            omega_per_motor=omega_per_motor,
            phase_radians=phase_radians,
            start_time_offset=start_time_offset,
            value_min=value_min if value_min is not None else SIGNAL_MIN_DEFAULT,
            value_max=value_max if value_max is not None else SIGNAL_MAX_DEFAULT,
        )
        
        # Attach to shared memory buffer
        shared_buffer = MotorStateBuffer(create=False)
        
        # CSV logging setup
        csv_file = None
        csv_writer = None
        if enable_logging:
            log_dir = Path('logs')
            log_dir.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            csv_path = log_dir / f'flight_log_{timestamp}.csv'
            csv_file = open(csv_path, 'w', newline='')
            
            # Create CSV header
            header = ['timestamp']
            header.extend([f'pwm_{i}' for i in range(NUM_MOTORS)])
            header.extend([f'rpm_{i}' for i in range(NUM_MOTORS)])
            
            csv_writer = csv.writer(csv_file)
            csv_writer.writerow(header)
            print(f"[FlightLoop] Logging enabled: {csv_path}")
        else:
            print("[FlightLoop] Logging disabled")
        
        # State tracking
        previous_pwm = np.full(NUM_MOTORS, PWM_CENTER, dtype=np.float64)
        active_slew_limit = slew_limit_override if slew_limit_override is not None else SLEW_LIMIT
        frame_count = 0
        loop_start_time = time.perf_counter()
        
        print("[FlightLoop] Ready to begin control loop")
        
        while not stop_event.is_set():
            frame_count += 1
            frame_time = time.perf_counter() - loop_start_time
            
            # --- Step 1: Generate physics signal (0.0 to 1.0) ---
            signal_raw = signal_gen.get_flow_field(frame_time)
            
            # --- Step 2: Map signal to PWM range (1000-2000) ---
            pwm_target = PWM_MIN + signal_raw * (PWM_MAX - PWM_MIN)
            
            # --- Step 3: Apply safety constraints ---
            # Calculate delta from previous PWM
            pwm_delta = pwm_target - previous_pwm
            
            # Clamp delta to slew limit
            pwm_delta_clamped = np.clip(pwm_delta, -active_slew_limit, active_slew_limit)
            
            # Compute safe PWM
            pwm_safe = previous_pwm + pwm_delta_clamped
            
            # Final clamp to valid PWM range
            pwm_safe = np.clip(pwm_safe, PWM_MIN, PWM_MAX)
            
            # --- Step 4: Send to hardware ---
            hardware.send_pwm(pwm_safe)
            
            # --- Step 5: Update shared memory ---
            shared_buffer.set_pwm(pwm_safe)
            
            # --- Step 6: Log to CSV (if enabled) ---
            if enable_logging and csv_writer and frame_count % log_interval_frames == 0:
                timestamp = datetime.now().isoformat()
                row = [timestamp]
                row.extend(pwm_safe.tolist())
                row.extend([0.0] * NUM_MOTORS)  # RPM placeholder (mock hardware)
                csv_writer.writerow(row)
                csv_file.flush()  # Ensure data is written
            
            # --- Step 7: Update state for next iteration ---
            previous_pwm = pwm_safe
            
            # --- Step 8: Spinlock until exactly 2.5 ms has elapsed ---
            target_time = loop_start_time + (frame_count * LOOP_TIME_MS / 1000.0)
            while time.perf_counter() < target_time:
                pass  # Busy-wait for deterministic timing
            
            # Periodic status (every 100 frames = 250 ms)
            if frame_count % 100 == 0:
                elapsed = time.perf_counter() - loop_start_time
                actual_rate = frame_count / elapsed if elapsed > 0 else 0
                avg_pwm = pwm_safe.mean()
                log_status = "(logging)" if enable_logging else "(no log)"
                print(f"[FlightLoop] Frame {frame_count:6d} | "
                      f"Rate: {actual_rate:.1f} Hz | Avg PWM: {avg_pwm:.0f} {log_status}")
    
    except Exception as e:
        print(f"[FlightLoop] FATAL ERROR: {e}")
        raise
    
    finally:
        print("[FlightLoop] Shutting down...")
        if 'csv_file' in locals() and csv_file:
            csv_file.close()
            print("[FlightLoop] CSV log file closed")
        if 'hardware' in locals():
            hardware.close()
        if 'shared_buffer' in locals():
            shared_buffer.close()
        print("[FlightLoop] Shutdown complete")
