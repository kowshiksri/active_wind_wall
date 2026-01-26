"""
Test function to visualize signal generation, Fourier reconstruction, and PWM output.
"""

import numpy as np
import matplotlib.pyplot as plt
import time
import threading
from multiprocessing import Process, Event
import signal

from config import NUM_MOTORS, UPDATE_RATE_HZ
from src.core import MotorStateBuffer
from src.core.flight_loop import flight_loop
from src.physics import SignalGenerator
from src.physics.signal_designer import generate_square_pulse


def run_flight_loop_thread(stop_event, coeffs, duration=3.0):
    """Run flight_loop in a separate thread and collect data."""
    
    # Initialize shared memory
    shared_buffer = MotorStateBuffer(create=True)
    
    # Create and start flight process
    flight_process = Process(
        target=flight_loop,
        args=(stop_event, True, coeffs),
        name="FlightLoop",
        daemon=False
    )
    flight_process.start()
    time.sleep(0.5)  # Let it initialize
    
    # Collect data
    data = {
        'time': [],
        'pwm': [],
        'signal_reconstructed': [],
        'signal_ideal': []
    }
    
    start_time = time.perf_counter()
    
    while time.perf_counter() - start_time < duration:
        try:
            pwm_current = shared_buffer.get_pwm()
            elapsed = time.perf_counter() - start_time
            
            data['time'].append(elapsed)
            data['pwm'].append(pwm_current[0])  # Store first motor
            
            time.sleep(0.01)  # 100 ms sampling
        except:
            pass
    
    # Stop flight process
    stop_event.set()
    flight_process.join(timeout=2)
    if flight_process.is_alive():
        flight_process.terminate()
        flight_process.join()
    
    shared_buffer.close()
    shared_buffer.unlink()
    
    return data


def test_square_wave():
    """Test with a 1 second period square wave."""
    
    print("="*70)
    print("Signal Generation Test: 1 Second Period Square Wave")
    print("="*70)
    
    # Generate square wave Fourier coefficients (1 sec period, 50% duty cycle)
    print("\n[Test] Generating square wave Fourier coefficients...")
    fourier_coeffs = generate_square_pulse(
        n_motors=NUM_MOTORS,
        amplitude=1.0,
        period=1.0,  # 1 second period
        duty_cycle=0.5,  # 50% on, 50% off
        n_terms=7
    )
    print(f"[Test] Coefficients shape: {fourier_coeffs.shape}")
    
    # Create signal generator for reference
    signal_gen = SignalGenerator(fourier_coeffs, base_freq=1.0)
    
    # Generate ideal perfect square wave (what we WANT)
    ideal_time = np.linspace(0, 3.0, 1200)
    ideal_signal = np.array([
        1.0 if (t % 1.0) < 0.5 else 0.0  # Perfect square wave
        for t in ideal_time
    ])
    
    # Generate Fourier reconstruction (what we CAN get with limited harmonics)
    fourier_time = np.linspace(0, 3.0, 1200)
    fourier_signal = np.array([signal_gen.get_flow_field(t)[0] for t in fourier_time])
    
    # Run flight loop and collect data
    print("\n[Test] Running flight loop for 3 seconds...")
    stop_event = Event()
    
    def run_with_timeout():
        data = run_flight_loop_thread(stop_event, fourier_coeffs, duration=3.0)
        return data
    
    data = run_flight_loop_thread(stop_event, fourier_coeffs, duration=3.0)
    
    print(f"[Test] Collected {len(data['time'])} samples")
    
    # Plot results
    print("\n[Test] Generating plot...")
    fig, axes = plt.subplots(3, 1, figsize=(14, 12))
    
    # Convert PWM to normalized signal for comparison
    pwm_normalized = [(pwm - 1000.0) / 1000.0 for pwm in data['pwm']]
    
    # Plot 1: All three signals - what we WANT, what we CAN get, what we SEND
    axes[0].plot(ideal_time, ideal_signal, 'k--', linewidth=2.5, label='Ideal Square Wave (what we want)', alpha=0.6, zorder=1)
    axes[0].plot(fourier_time, fourier_signal, 'b-', linewidth=2, label='Fourier Reconstruction (7 harmonics)', alpha=0.8, zorder=2)
    axes[0].plot(data['time'], pwm_normalized, 'r-', linewidth=1.5, label='PWM Output (what we send)', alpha=0.9, zorder=3)
    axes[0].set_ylabel('Signal Value [0.0 - 1.0]', fontsize=11)
    axes[0].set_xlabel('Time [s]', fontsize=11)
    axes[0].set_title('Signal Comparison: Ideal vs Fourier vs PWM', fontsize=12, fontweight='bold')
    axes[0].grid(True, alpha=0.3)
    axes[0].legend(loc='upper right', fontsize=9)
    axes[0].set_ylim([-0.15, 1.15])
    
    # Plot 2: Comparison between Fourier reconstruction and ideal (the error)
    axes[1].plot(ideal_time, ideal_signal, 'k--', linewidth=2, label='Ideal Square Wave', alpha=0.6)
    axes[1].plot(fourier_time, fourier_signal, 'b-', linewidth=2, label='Fourier Reconstruction (7 harmonics)', alpha=0.8)
    # Add difference shading
    ideal_interp = np.interp(fourier_time, ideal_time, ideal_signal)
    axes[1].fill_between(fourier_time, ideal_interp, fourier_signal, alpha=0.3, color='orange', label='Approximation Error')
    axes[1].set_ylabel('Signal Value [0.0 - 1.0]', fontsize=11)
    axes[1].set_xlabel('Time [s]', fontsize=11)
    axes[1].set_title('Fourier Approximation vs Ideal (Gibbs Phenomenon Visible)', fontsize=12, fontweight='bold')
    axes[1].grid(True, alpha=0.3)
    axes[1].legend(loc='upper right', fontsize=9)
    axes[1].set_ylim([-0.15, 1.15])
    
    # Plot 3: Signal decomposition (first few Fourier terms for motor 0)
    print("\n[Test] Fourier coefficients for Motor 0:")
    coeffs_motor0 = fourier_coeffs[0]
    harmonic_nums = np.arange(1, len(coeffs_motor0) + 1)
    colors = ['purple' if c > 0 else 'orange' for c in coeffs_motor0]
    axes[2].bar(harmonic_nums, coeffs_motor0, color=colors, alpha=0.7, edgecolor='black', linewidth=1)
    axes[2].axhline(y=0, color='black', linestyle='-', linewidth=0.8)
    axes[2].set_xlabel('Harmonic Number', fontsize=11)
    axes[2].set_ylabel('Coefficient Amplitude', fontsize=11)
    axes[2].set_title('Fourier Coefficients (Square Wave Decomposition)', fontsize=12, fontweight='bold')
    axes[2].grid(True, alpha=0.3, axis='y')
    axes[2].set_xticks(harmonic_nums)
    
    for i, coeff in enumerate(coeffs_motor0):
        print(f"  Harmonic {i+1}: {coeff:.6f}")
    
    plt.tight_layout()
    
    # Save and show
    output_file = '/Users/kowshiksrivatsan/Desktop/ISM_WiMi/active_wind_wall/test_signal_output.png'
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    print(f"\n[Test] Plot saved to: {output_file}")
    
    plt.show()
    
    # Print statistics
    print("\n" + "="*70)
    print("Test Summary")
    print("="*70)
    print(f"Period: 1.0 seconds")
    print(f"Duty cycle: 50% (0.5 sec on, 0.5 sec off)")
    print(f"Duration: 3.0 seconds (~3 cycles)")
    print(f"Samples collected: {len(data['time'])}")
    print(f"Sample rate: {len(data['time'])/3.0:.1f} Hz")
    print(f"PWM min: {min(data['pwm']):.0f} µs")
    print(f"PWM max: {max(data['pwm']):.0f} µs")
    print(f"PWM mean: {np.mean(data['pwm']):.0f} µs")
    print("="*70)


if __name__ == '__main__':
    test_square_wave()
