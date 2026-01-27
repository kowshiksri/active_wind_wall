"""
Main entry point for the Active Wind Wall Control System.
Launches flight_loop process and waits for termination.
"""

import multiprocessing
multiprocessing.set_start_method('fork', force=True)
import sys
import signal
import time
import numpy as np

from config import (
    NUM_MOTORS,
    BASE_FREQUENCY,
    EXPERIMENT_DURATION_S,
    SIGNAL_MIN_DEFAULT,
    SIGNAL_MAX_DEFAULT,
)
from src.core import MotorStateBuffer
from src.core.flight_loop import flight_loop
from src.physics.signal_designer import generate_square_pulse


def main(
    fourier_coeffs: np.ndarray | None = None,
    experiment_duration_s: float | None = EXPERIMENT_DURATION_S,
    start_delay_s: float = 0.0,
    value_min: float = SIGNAL_MIN_DEFAULT,
    value_max: float = SIGNAL_MAX_DEFAULT,
    enable_logging: bool = True,
) -> None:
    """
    Main entry point.
    Sets up multiprocessing, initializes shared memory, and launches flight_loop.
    
    Args:
        fourier_coeffs: Pre-computed Fourier coefficient matrix [n_motors, n_terms]
                       If None, generates default square wave pattern
    """
    print("="*70)
    print("Active Wind Wall Control System v0.1")
    print("="*70)
    
    # Generate default coefficients if none provided
    if fourier_coeffs is None:
        print("[Main] Generating default square wave pattern...")
        default_period = 10.0
        default_base_freq = 1.0 / default_period
        # amplitude parameter is HALF the peak-to-peak range; 0.5 gives swing 0..1 after DC set
        fourier_coeffs = generate_square_pulse(
            n_motors=NUM_MOTORS,
            amplitude=0.5,
            period=default_period,
            duty_cycle=0.5,
            n_terms=7,
            base_freq=default_base_freq,
        )
        # Set DC to midpoint 0.5 so output spans [0,1]
        fourier_coeffs[:, 0] = 0.5
        # Per-motor omega array (all motors share the same default period here)
        omega_per_motor = np.full(NUM_MOTORS, 2.0 * np.pi * default_base_freq, dtype=float)
    else:
        # If user provides coeffs, use uniform omega based on BASE_FREQUENCY
        omega_per_motor = np.full(NUM_MOTORS, 2.0 * np.pi * BASE_FREQUENCY, dtype=float)
    
    print(f"[Main] Signal shape: {fourier_coeffs.shape}")
    
    # Create stop event for clean shutdown
    stop_event = multiprocessing.Event()
    
    # Initialize shared memory
    print("[Main] Initializing shared memory buffer...")
    try:
        shared_buffer = MotorStateBuffer(create=True)
        print(f"[Main] Shared memory initialized: {NUM_MOTORS} motors, "
              f"shape={shared_buffer.shape}")
    except Exception as e:
        print(f"[Main] FATAL: Could not create shared memory: {e}")
        sys.exit(1)
    
    # Determine if using mock hardware (auto-detect platform)
    import platform
    use_mock = platform.system() == "Darwin"
    print(f"[Main] Platform: {platform.system()}")
    print(f"[Main] Hardware mode: {'MOCK (macOS)' if use_mock else 'REAL (Linux/RPi)'}")
    
    # Launch flight control process
    print(f"[Main] Launching flight_loop process (logging={'ON' if enable_logging else 'OFF'})...")
    flight_process = multiprocessing.Process(
        target=flight_loop,
        args=(stop_event, use_mock, fourier_coeffs, BASE_FREQUENCY, omega_per_motor, None, start_delay_s, value_min, value_max, enable_logging),
        name="FlightLoop",
        daemon=False
    )
    flight_process.start()
    
    # Give flight process time to initialize
    time.sleep(0.5)
    
    if not flight_process.is_alive():
        print("[Main] ERROR: flight_process failed to start!")
        shared_buffer.unlink()
        sys.exit(1)
    
    print("[Main] Flight loop running. Press Ctrl+C to stop.")
    start_wall = time.perf_counter()
    
    try:
        # Handle Ctrl+C gracefully
        def signal_handler(sig, frame):
            print("\n[Main] Ctrl+C detected, shutting down...")
            stop_event.set()
        
        signal.signal(signal.SIGINT, signal_handler)
        
        # Monitor for duration or manual stop
        while flight_process.is_alive():
            time.sleep(0.1)
            if stop_event.is_set():
                break
            if experiment_duration_s is not None:
                elapsed = time.perf_counter() - start_wall
                if elapsed >= experiment_duration_s:
                    print(f"[Main] Experiment duration reached ({experiment_duration_s}s); stopping...")
                    stop_event.set()
                    break
        
        # Ensure process exits
        flight_process.join(timeout=2)
    
    except Exception as e:
        print(f"[Main] Error: {e}")
    
    finally:
        # Cleanup
        print("[Main] Cleaning up...")
        stop_event.set()
        
        # Wait for flight process to finish
        flight_process.join(timeout=2)
        if flight_process.is_alive():
            print("[Main] Force-terminating flight_process...")
            flight_process.terminate()
            flight_process.join()
        
        # Cleanup shared memory
        shared_buffer.unlink()
        print("[Main] All processes terminated")
        print("="*70)


if __name__ == '__main__':
    main()
