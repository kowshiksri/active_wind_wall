"""
High-speed flight control loop (Process A).
Runs at 400 Hz with deterministic timing and safety checks.
"""

import time
import numpy as np
from multiprocessing import Event
from config import (
    NUM_MOTORS, UPDATE_RATE_HZ, PWM_MIN, PWM_MAX, PWM_CENTER,
    SLEW_LIMIT, LOOP_TIME_MS
)
from src.hardware import HardwareInterface
from src.physics import SignalGenerator
from src.core import MotorStateBuffer


def flight_loop(stop_event: Event, use_mock_hardware: bool = True, fourier_coeffs: np.ndarray = None) -> None: # type: ignore
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
    """
    print(f"[FlightLoop] Initializing at {UPDATE_RATE_HZ} Hz ({LOOP_TIME_MS:.2f} ms)")
    
    try:
        # Initialize hardware interface with platform detection
        hardware = HardwareInterface(use_mock=use_mock_hardware)
        
        # Initialize physics engine with coefficient matrix
        if fourier_coeffs is None:
            raise ValueError("fourier_coeffs must be provided to flight_loop")
        signal_gen = SignalGenerator(fourier_coeffs)
        
        # Attach to shared memory buffer
        shared_buffer = MotorStateBuffer(create=False)
        
        # State tracking
        previous_pwm = np.full(NUM_MOTORS, PWM_CENTER, dtype=np.float64)
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
            pwm_delta_clamped = np.clip(pwm_delta, -SLEW_LIMIT, SLEW_LIMIT)
            
            # Compute safe PWM
            pwm_safe = previous_pwm + pwm_delta_clamped
            
            # Final clamp to valid PWM range
            pwm_safe = np.clip(pwm_safe, PWM_MIN, PWM_MAX)
            
            # --- Step 4: Send to hardware ---
            hardware.send_pwm(pwm_safe)
            
            # --- Step 5: Update shared memory ---
            shared_buffer.set_pwm(pwm_safe)
            
            # --- Step 6: Update state for next iteration ---
            previous_pwm = pwm_safe
            
            # --- Step 7: Spinlock until exactly 2.5 ms has elapsed ---
            target_time = loop_start_time + (frame_count * LOOP_TIME_MS / 1000.0)
            while time.perf_counter() < target_time:
                pass  # Busy-wait for deterministic timing
            
            # Periodic status (every 100 frames = 250 ms)
            if frame_count % 100 == 0:
                elapsed = time.perf_counter() - loop_start_time
                actual_rate = frame_count / elapsed if elapsed > 0 else 0
                avg_pwm = pwm_safe.mean()
                print(f"[FlightLoop] Frame {frame_count:6d} | "
                      f"Rate: {actual_rate:.1f} Hz | Avg PWM: {avg_pwm:.0f}")
    
    except Exception as e:
        print(f"[FlightLoop] FATAL ERROR: {e}")
        raise
    
    finally:
        print("[FlightLoop] Shutting down...")
        if 'hardware' in locals():
            hardware.close()
        if 'shared_buffer' in locals():
            shared_buffer.close()
        print("[FlightLoop] Shutdown complete")
