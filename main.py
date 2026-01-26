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

from config import NUM_MOTORS
from src.core import MotorStateBuffer
from src.core.flight_loop import flight_loop
from src.physics.signal_designer import generate_square_pulse


def main(fourier_coeffs: np.ndarray = None) -> None:
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
        fourier_coeffs = generate_square_pulse(
            n_motors=NUM_MOTORS,
            amplitude=1.0,
            period=10.0,
            duty_cycle=0.5
        )
    
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
    print("[Main] Launching flight_loop process...")
    flight_process = multiprocessing.Process(
        target=flight_loop,
        args=(stop_event, use_mock, fourier_coeffs),
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
    
    try:
        # Handle Ctrl+C gracefully
        def signal_handler(sig, frame):
            print("\n[Main] Ctrl+C detected, shutting down...")
            stop_event.set()
        
        signal.signal(signal.SIGINT, signal_handler)
        
        # Wait for process to finish
        flight_process.join()
    
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
