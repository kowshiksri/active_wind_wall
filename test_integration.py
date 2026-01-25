#!/usr/bin/env python3
"""
Integration test suite for Active Wind Wall Control System v0.1
Tests all major components in isolation before running full system.
"""

import sys
import time
import numpy as np

sys.path.insert(0, '.')


def test_config():
    """Test configuration constants."""
    print("\n" + "="*70)
    print("TEST 1: Configuration Module")
    print("="*70)
    
    from config import (
        NUM_MOTORS, UPDATE_RATE_HZ, PWM_MIN, PWM_MAX, PWM_CENTER,
        SLEW_LIMIT, HARMONICS, BASE_FREQUENCY, LOOP_TIME_MS
    )
    
    print(f"✓ NUM_MOTORS:        {NUM_MOTORS}")
    print(f"✓ UPDATE_RATE_HZ:    {UPDATE_RATE_HZ} Hz")
    print(f"✓ LOOP_TIME_MS:      {LOOP_TIME_MS:.2f} ms")
    print(f"✓ PWM_MIN/MAX/CENTER: {PWM_MIN}/{PWM_MAX}/{PWM_CENTER} µs")
    print(f"✓ SLEW_LIMIT:        {SLEW_LIMIT} units/tick")
    print(f"✓ HARMONICS:         {HARMONICS}")
    print(f"✓ BASE_FREQUENCY:    {BASE_FREQUENCY} Hz")
    
    assert NUM_MOTORS == 36
    assert UPDATE_RATE_HZ == 400
    assert PWM_MIN == 1000 and PWM_MAX == 2000
    assert SLEW_LIMIT == 50
    assert HARMONICS == [1, 3, 5, 7]
    print("\n✓ Configuration OK")


def test_physics():
    """Test signal generation."""
    print("\n" + "="*70)
    print("TEST 2: Physics Engine (Signal Generation)")
    print("="*70)
    
    from src.physics import SignalGenerator
    from config import NUM_MOTORS
    
    sg = SignalGenerator()
    print(f"✓ SignalGenerator created")
    
    # Test at t=0
    signal_t0 = sg.get_flow_field(0.0)
    assert signal_t0.shape == (NUM_MOTORS,)
    assert signal_t0.dtype == np.float64
    assert np.all(signal_t0 >= 0.0) and np.all(signal_t0 <= 1.0)
    print(f"✓ Signal at t=0.0:   min={signal_t0.min():.4f}, "
          f"max={signal_t0.max():.4f}, mean={signal_t0.mean():.4f}")
    
    # Test frequency change
    sg.set_frequency(2.0)
    signal_2hz = sg.get_flow_field(0.0)
    print(f"✓ Signal at 2 Hz:    min={signal_2hz.min():.4f}, "
          f"max={signal_2hz.max():.4f}, mean={signal_2hz.mean():.4f}")
    
    # Test vectorization (all motors same signal)
    assert np.allclose(signal_t0, signal_t0[0])
    print(f"✓ All 36 motors synchronized (broadcasting works)")
    
    # Test time evolution
    times = np.linspace(0, 0.01, 100)  # 10 ms window
    signals = np.array([sg.get_flow_field(t) for t in times])
    signal_variance = signals.var()
    assert signal_variance > 0.001, "Signal should vary over time"
    print(f"✓ Signal variance over 10 ms: {signal_variance:.6f} (expected >0.001)")
    
    print("\n✓ Physics Engine OK")


def test_hardware():
    """Test hardware abstraction layer."""
    print("\n" + "="*70)
    print("TEST 3: Hardware Interface (Mock Mode)")
    print("="*70)
    
    from src.hardware import HardwareInterface
    import platform
    
    hw = HardwareInterface(use_mock=True)
    detected_platform = platform.system()
    print(f"✓ Platform detected: {detected_platform}")
    print(f"✓ Using MOCK drivers (safe for {detected_platform})")
    
    # Test PWM transmission
    pwm_values = np.full(36, 1500.0)
    rpm_response = hw.send_pwm(pwm_values)
    
    assert rpm_response.shape == (36,)
    assert rpm_response.dtype == np.float64
    print(f"✓ Sent 36 PWM values @ 1500 µs")
    print(f"✓ Received 36 RPM telemetry values")
    
    # Test with varying PWM
    pwm_ramp = np.linspace(1000, 2000, 36)
    rpm_response = hw.send_pwm(pwm_ramp)
    print(f"✓ PWM ramp: {pwm_ramp.min():.0f}-{pwm_ramp.max():.0f} µs")
    
    hw.close()
    print("\n✓ Hardware Interface OK")


def test_shared_memory():
    """Test inter-process shared memory."""
    print("\n" + "="*70)
    print("TEST 4: Shared Memory Buffer")
    print("="*70)
    
    from src.core import MotorStateBuffer
    
    # Create buffer
    buffer = MotorStateBuffer(create=True)
    print(f"✓ Created shared memory buffer")
    print(f"  Shape: {buffer.shape}")
    print(f"  Dtype: {buffer.dtype}")
    print(f"  Name:  {buffer.name}")
    
    # Write test data
    test_pwm = np.linspace(1000, 2000, 36)
    test_rpm = np.random.randint(0, 10000, 36).astype(np.float64)
    
    buffer.set_pwm(test_pwm)
    buffer.set_rpm(test_rpm)
    print(f"✓ Wrote test data")
    
    # Read back and verify
    pwm_read = buffer.get_pwm()
    rpm_read = buffer.get_rpm()
    
    assert np.allclose(pwm_read, test_pwm)
    assert np.allclose(rpm_read, test_rpm)
    print(f"✓ PWM verified: range [{pwm_read.min():.0f}, {pwm_read.max():.0f}]")
    print(f"✓ RPM verified: range [{rpm_read.min():.0f}, {rpm_read.max():.0f}]")
    
    # Get all data
    all_data = buffer.get_all()
    assert all_data.shape == (36, 2)
    print(f"✓ Full buffer read: shape={all_data.shape}")
    
    # Cleanup
    buffer.unlink()
    print(f"✓ Buffer unlinked")
    print("\n✓ Shared Memory OK")


def test_flight_loop_simulation():
    """Simulate flight loop operation without multiprocessing."""
    print("\n" + "="*70)
    print("TEST 5: Flight Loop Simulation (Mock Process)")
    print("="*70)
    
    from src.physics import SignalGenerator
    from src.hardware import HardwareInterface
    from src.core import MotorStateBuffer
    from config import (
        PWM_MIN, PWM_MAX, SLEW_LIMIT, UPDATE_RATE_HZ, LOOP_TIME_MS, NUM_MOTORS
    )
    import time as time_module
    
    # Initialize components
    sg = SignalGenerator()
    hw = HardwareInterface(use_mock=True)
    buffer = MotorStateBuffer(create=True)
    
    print(f"✓ Components initialized")
    
    # Simulate 10 control cycles
    previous_pwm = np.full(NUM_MOTORS, 1500.0)
    loop_start = time_module.perf_counter()
    
    for frame in range(10):
        t = (frame * LOOP_TIME_MS) / 1000.0
        
        # Step 1: Physics
        signal = sg.get_flow_field(t)
        
        # Step 2: Map to PWM
        pwm_target = PWM_MIN + signal * (PWM_MAX - PWM_MIN)
        
        # Step 3: Safety limiting
        pwm_delta = pwm_target - previous_pwm
        pwm_delta_clamped = np.clip(pwm_delta, -SLEW_LIMIT, SLEW_LIMIT)
        pwm_safe = previous_pwm + pwm_delta_clamped
        pwm_safe = np.clip(pwm_safe, PWM_MIN, PWM_MAX)
        
        # Step 4: Hardware send (mock)
        rpm_telemetry = hw.send_pwm(pwm_safe)
        
        # Step 5: Shared memory update
        buffer.set_pwm(pwm_safe)
        buffer.set_rpm(rpm_telemetry)
        
        # Step 6: Update state
        previous_pwm = pwm_safe
        
        if frame == 0:
            print(f"✓ Frame {frame:2d}: signal={signal.mean():.3f}, "
                  f"pwm={pwm_safe.mean():.0f}, delta={pwm_delta.mean():.2f}")
        elif frame == 9:
            print(f"✓ Frame {frame:2d}: signal={signal.mean():.3f}, "
                  f"pwm={pwm_safe.mean():.0f}, delta={pwm_delta.mean():.2f}")
    
    elapsed = time_module.perf_counter() - loop_start
    print(f"✓ Simulated 10 frames in {elapsed*1000:.2f} ms")
    print(f"✓ Physics: signal evolution captured")
    print(f"✓ Safety: slew limiting applied")
    print(f"✓ Shared memory: updated every frame")
    
    # Cleanup
    hw.close()
    buffer.unlink()
    print("\n✓ Flight Loop Simulation OK")


def main():
    """Run all tests."""
    print("\n")
    print("╔" + "="*68 + "╗")
    print("║" + " "*68 + "║")
    print("║" + "  ACTIVE WIND WALL CONTROL SYSTEM v0.1 - INTEGRATION TEST".center(68) + "║")
    print("║" + " "*68 + "║")
    print("╚" + "="*68 + "╝")
    
    try:
        test_config()
        test_physics()
        test_hardware()
        test_shared_memory()
        test_flight_loop_simulation()
        
        print("\n" + "="*70)
        print("ALL TESTS PASSED ✓".center(70))
        print("="*70)
        print("\nSystem is ready for deployment!")
        print("Run: python3 main.py")
        print("="*70 + "\n")
        
        return 0
    
    except Exception as e:
        print("\n" + "="*70)
        print("TEST FAILED ✗".center(70))
        print("="*70)
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        print("="*70 + "\n")
        return 1


if __name__ == '__main__':
    sys.exit(main())
