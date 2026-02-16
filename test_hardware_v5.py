#!/usr/bin/env python3
"""
Test Hardware Control Script - v5 (Works with pico_test_v5.c)
Simple SPI communication for real-time PWM control.

This is a simplified version based on the colleague's working approach:
- No GPIO trigger needed
- Continuous SPI polling
- Send byte values (0-255) that map to PWM range (1000-2000µs)
"""

import spidev
import time
import sys

class SimpleMotorController:
    def __init__(self, num_motors=2, speed=1000000):
        """Initialize SPI connection"""
        self.num_motors = num_motors
        self.motor_values = [0] * num_motors
        
        self.spi = spidev.SpiDev()
        try:
            self.spi.open(0, 0)  # SPI bus 0, device 0
        except Exception as e:
            print(f"✗ Failed to open SPI: {e}")
            print("  Make sure you have SPI enabled and permissions set")
            sys.exit(1)
        
        self.spi.mode = 0
        self.spi.max_speed_hz = speed
        
        print("="*70)
        print("SIMPLE MOTOR CONTROL - v5")
        print("="*70)
        print(f"SPI: Bus 0, Device 0, Speed {speed/1000000:.1f} MHz")
        print(f"Controlling {num_motors} motor(s)")
        print("GPIO17: CS, GPIO16: MOSI (Data), GPIO18: SCK (Clock)")
        print("Motor PWM Range: 1000-2000µs (0-255 byte mapping)")
        print("="*70)
    
    def _intensity_to_byte(self, intensity):
        """Convert 0-100% intensity to 0-255 byte"""
        if intensity < 0:
            intensity = 0
        if intensity > 100:
            intensity = 100
        return int((intensity * 255) / 100)
    
    def _byte_to_us(self, byte_val):
        """Convert 0-255 byte to microseconds"""
        return 1000 + (byte_val * 1000) / 255
    
    def send_to_pico(self, values):
        """Send byte values to Pico via SPI"""
        try:
            # Ensure we have the right number of values
            data = values[:self.num_motors]
            
            # Send and receive response
            response = self.spi.xfer2(data)
            
            # Display what we sent and what we got back
            print("SPI Tx: ", end="")
            for i, val in enumerate(data):
                us = self._byte_to_us(val)
                print(f"M{i+1}: {val:3d} ({us:5.1f}µs) ", end="")
            
            print(f"| Rx: [{', '.join([f'0x{r:02X}' for r in response[:self.num_motors]])}]")
            return True
            
        except Exception as e:
            print(f"✗ SPI Error: {e}")
            return False
    
    def set_all_motors(self, intensity):
        """Set all motors to same intensity"""
        if not (0 <= intensity <= 100):
            print(f"Error: Intensity must be 0-100, got {intensity}")
            return False
        
        byte_val = self._intensity_to_byte(intensity)
        self.motor_values = [byte_val] * self.num_motors
        return self.send_to_pico(self.motor_values)
    
    def set_motor(self, motor_num, intensity):
        """Set specific motor"""
        if not (1 <= motor_num <= self.num_motors):
            print(f"Error: Motor {motor_num} out of range (1-{self.num_motors})")
            return False
        
        if not (0 <= intensity <= 100):
            print(f"Error: Intensity must be 0-100, got {intensity}")
            return False
        
        self.motor_values[motor_num - 1] = self._intensity_to_byte(intensity)
        return self.send_to_pico(self.motor_values)
    
    def sweep(self, start=0, end=100, steps=20, delay=0.2):
        """Sweep all motors smoothly"""
        print(f"\nSweeping all motors: {start}% → {end}% ({steps} steps)\n")
        
        for i in range(steps + 1):
            intensity = int(start + (i * (end - start) / steps))
            self.set_all_motors(intensity)
            time.sleep(delay)
        
        print()
    
    def test_sequence(self):
        """Run comprehensive test"""
        print("\n" + "="*70)
        print("TEST SEQUENCE")
        print("="*70)
        
        # Test 1: Start at minimum
        print("\n[1] Setting all motors to 0% (minimum)")
        self.set_all_motors(0)
        time.sleep(1)
        
        # Test 2: Jump to center
        print("\n[2] Jump to 50% (center)")
        self.set_all_motors(50)
        time.sleep(1)
        
        # Test 3: Jump to maximum
        print("\n[3] Jump to 100% (maximum)")
        self.set_all_motors(100)
        time.sleep(1)
        
        # Test 4: Smooth sweep
        print("\n[4] Smooth sweep: 0% → 100% → 0%")
        self.sweep(0, 100, steps=10, delay=0.1)
        self.sweep(100, 0, steps=10, delay=0.1)
        
        # Test 5: Back to center
        print("\n[5] Return to 50% (center)")
        self.set_all_motors(50)
        time.sleep(1)
        
        # Test 6: Back to minimum
        print("\n[6] Return to 0% (minimum)")
        self.set_all_motors(0)
        time.sleep(0.5)
        
        print("="*70)
        print("Test sequence complete!\n")
    
    def interactive_mode(self):
        """Interactive command mode"""
        print("\n" + "="*70)
        print("INTERACTIVE MODE")
        print("="*70)
        print("Commands:")
        print("  all <0-100>  : Set all motors to intensity")
        print("  m1 <0-100>   : Set motor 1 to intensity")
        print("  m2 <0-100>   : Set motor 2 to intensity")
        print("  sweep        : Sweep all motors 0→100→0")
        print("  test         : Run test sequence")
        print("  status       : Show current values")
        print("  quit         : Exit")
        print("="*70 + "\n")
        
        while True:
            try:
                cmd = input(">>> ").strip().split()
                
                if not cmd:
                    continue
                
                if cmd[0].lower() == 'quit':
                    break
                
                elif cmd[0].lower() == 'all':
                    if len(cmd) == 2:
                        intensity = int(cmd[1])
                        self.set_all_motors(intensity)
                    else:
                        print("Usage: all <0-100>")
                
                elif cmd[0].lower().startswith('m'):
                    if len(cmd) == 2:
                        motor_num = int(cmd[0][1:])
                        intensity = int(cmd[1])
                        self.set_motor(motor_num, intensity)
                    else:
                        print("Usage: mX <0-100>")
                
                elif cmd[0].lower() == 'sweep':
                    self.sweep()
                
                elif cmd[0].lower() == 'test':
                    self.test_sequence()
                
                elif cmd[0].lower() == 'status':
                    print("\nCurrent values:")
                    for i, val in enumerate(self.motor_values):
                        us = self._byte_to_us(val)
                        intensity = int((val * 100) / 255)
                        print(f"  Motor {i+1}: {intensity:3d}% ({val:3d}) → {us:5.1f}µs")
                    print()
                
                else:
                    print("Unknown command")
            
            except KeyboardInterrupt:
                print("\nExiting...")
                break
            except Exception as e:
                print(f"Error: {e}")
    
    def close(self):
        """Clean shutdown"""
        print("\nShutting down...")
        self.set_all_motors(0)
        time.sleep(0.1)
        self.spi.close()
        print("SPI closed")

def main():
    # Check for command line arguments for automation
    if len(sys.argv) > 1:
        # Command line mode for testing
        controller = SimpleMotorController(num_motors=2)
        
        try:
            if sys.argv[1] == 'test':
                controller.test_sequence()
            elif sys.argv[1] == 'sweep':
                controller.sweep(steps=20, delay=0.1)
            elif sys.argv[1].startswith('set'):
                # set:motor:intensity (e.g., set:1:75)
                parts = sys.argv[1].split(':')
                if len(parts) == 3:
                    motor = int(parts[1])
                    intensity = int(parts[2])
                    controller.set_motor(motor, intensity)
                else:
                    print("Usage: set:motor:intensity")
            else:
                print(f"Unknown command: {sys.argv[1]}")
        except Exception as e:
            print(f"Error: {e}")
        finally:
            controller.close()
    else:
        # Interactive mode
        controller = SimpleMotorController(num_motors=2)
        
        try:
            # Quick initialization
            print("\nInitializing motors to 0%...")
            controller.set_all_motors(0)
            time.sleep(0.5)
            
            # Main menu
            while True:
                print("\n" + "="*70)
                print("MAIN MENU")
                print("="*70)
                print("1. Interactive control")
                print("2. Run test sequence")
                print("3. Sweep test")
                print("4. Set all to 50%")
                print("5. Exit")
                print("="*70)
                
                choice = input("\nSelect (1-5): ").strip()
                
                if choice == '1':
                    controller.interactive_mode()
                elif choice == '2':
                    controller.test_sequence()
                elif choice == '3':
                    controller.sweep(steps=20, delay=0.1)
                elif choice == '4':
                    controller.set_all_motors(50)
                    time.sleep(2)
                elif choice == '5':
                    break
                else:
                    print("Invalid choice")
        
        except KeyboardInterrupt:
            print("\n\nInterrupted by user")
        except Exception as e:
            print(f"\nError: {e}")
        finally:
            controller.close()

if __name__ == "__main__":
    main()
