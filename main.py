"""
Main entry point for the Active Wind Wall Control System.
Orchestrates Process A (flight_loop) and Process B (GUI dashboard).
"""

import multiprocessing
multiprocessing.set_start_method('fork', force=True)
import sys
import signal
import multiprocessing as mp
from multiprocessing import Process, Event
import time

from config import NUM_MOTORS
from src.core import MotorStateBuffer
from src.core.flight_loop import flight_loop
from src.gui import launch_dashboard
from src.gui import launch_dashboard

def main() -> None:
    """
    Main entry point.
    Sets up multiprocessing, initializes shared memory, and launches processes.
    """
    print("="*70)
    print("Active Wind Wall Control System v0.1")
    print("="*70)
    
    # Create stop event for clean shutdown
    stop_event = Event()
    
    # Initialize shared memory (Process A will attach, Process B will attach)
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
    
    # Launch flight control process (Process A)
    print("[Main] Launching flight_loop process...")
    flight_process = Process(
        target=flight_loop,
        args=(stop_event, use_mock),
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
    
    # Launch GUI (Process B in main thread)
    print("[Main] Launching GUI dashboard...")
    try:
        # Handle Ctrl+C gracefully
        def signal_handler(sig, frame):
            print("\n[Main] Ctrl+C detected, shutting down...")
            stop_event.set()
            flight_process.join(timeout=2)
            if flight_process.is_alive():
                flight_process.terminate()
                flight_process.join()
            shared_buffer.unlink()
            print("[Main] Shutdown complete")
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        
        # Start GUI (blocks until window closes)
        launch_dashboard()
    
    except Exception as e:
        print(f"[Main] GUI error: {e}")
    
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

    print("[Main] Launching GUI dashboard...")
    launch_dashboard()
    print("[Main] GUI closed, exiting")


if __name__ == '__main__':
    main()
