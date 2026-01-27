#!/usr/bin/env python3
"""
GUI Interface for Active Wind Wall Control System.
Standalone interface that uses existing codebase without modifications.
"""

import sys
import numpy as np
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox, QSpinBox, QDoubleSpinBox,
    QGridLayout, QGroupBox, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
import multiprocessing

from config import NUM_MOTORS, PWM_MIN
from src.physics.signal_designer import generate_sine_wave, generate_square_pulse, generate_uniform
from main import main


class MotorButton(QPushButton):
    """Custom button for motor selection."""
    
    def __init__(self, motor_id):
        super().__init__(str(motor_id))
        self.motor_id = motor_id
        self.is_active = False
        self.setCheckable(True)
        self.setMinimumSize(60, 60)
        self.setMaximumSize(60, 60)
        self.update_style()
        self.clicked.connect(self.toggle_active)
    
    def toggle_active(self):
        """Toggle motor active state."""
        self.is_active = self.isChecked()
        self.update_style()
    
    def update_style(self):
        """Update button appearance based on state."""
        if self.is_active:
            self.setStyleSheet("""
                QPushButton {
                    background-color: #4CAF50;
                    color: white;
                    border: 2px solid #45a049;
                    border-radius: 8px;
                    font-weight: bold;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #45a049;
                }
            """)
        else:
            self.setStyleSheet("""
                QPushButton {
                    background-color: #cccccc;
                    color: #666666;
                    border: 2px solid #999999;
                    border-radius: 8px;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #bbbbbb;
                }
            """)


class WindWallGUI(QMainWindow):
    """Main GUI window for Active Wind Wall control."""
    
    def __init__(self):
        super().__init__()
        self.motor_buttons = []
        self.experiment_running = False
        self.flight_process = None
        self.stop_event = None
        self.shared_buffer = None
        self.init_ui()
    
    def init_ui(self):
        """Initialize the user interface."""
        self.setWindowTitle("Active Wind Wall Control Interface")
        self.setGeometry(100, 100, 1000, 700)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        
        # Left panel - Signal configuration
        config_panel = self.create_config_panel()
        main_layout.addWidget(config_panel, stretch=1)
        
        # Center panel - Motor grid
        grid_panel = self.create_grid_panel()
        main_layout.addWidget(grid_panel, stretch=2)
        
        # Right panel - Info and controls
        control_panel = self.create_control_panel()
        main_layout.addWidget(control_panel, stretch=1)
    
    def create_config_panel(self):
        """Create signal configuration panel."""
        group = QGroupBox("Signal Configuration")
        layout = QVBoxLayout()
        
        # Signal type
        layout.addWidget(QLabel("Signal Type:"))
        self.signal_type = QComboBox()
        self.signal_type.addItems(["Sine Wave", "Square Wave", "Constant (Off)"])
        layout.addWidget(self.signal_type)
        
        layout.addSpacing(10)
        
        # Amplitude minimum
        layout.addWidget(QLabel("Amplitude Min (0.0-1.0):"))
        self.amp_min = QDoubleSpinBox()
        self.amp_min.setRange(0.0, 1.0)
        self.amp_min.setSingleStep(0.05)
        self.amp_min.setValue(0.25)
        self.amp_min.setDecimals(2)
        layout.addWidget(self.amp_min)
        
        # Amplitude maximum
        layout.addWidget(QLabel("Amplitude Max (0.0-1.0):"))
        self.amp_max = QDoubleSpinBox()
        self.amp_max.setRange(0.0, 1.0)
        self.amp_max.setSingleStep(0.05)
        self.amp_max.setValue(0.75)
        self.amp_max.setDecimals(2)
        layout.addWidget(self.amp_max)
        
        layout.addSpacing(10)
        
        # Period
        layout.addWidget(QLabel("Period (seconds):"))
        self.period = QDoubleSpinBox()
        self.period.setRange(0.1, 60.0)
        self.period.setSingleStep(0.5)
        self.period.setValue(2.0)
        self.period.setDecimals(1)
        layout.addWidget(self.period)
        
        # Fourier terms
        layout.addWidget(QLabel("Fourier Terms:"))
        self.fourier_terms = QSpinBox()
        self.fourier_terms.setRange(1, 20)
        self.fourier_terms.setValue(7)
        layout.addWidget(self.fourier_terms)
        
        layout.addStretch()
        group.setLayout(layout)
        return group
    
    def create_grid_panel(self):
        """Create motor grid panel."""
        group = QGroupBox("Motor Grid (6×6)")
        layout = QVBoxLayout()
        
        # Instructions
        info_label = QLabel("Click motors to activate/deactivate")
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_label.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(info_label)
        
        # Grid layout for motors
        grid = QGridLayout()
        grid.setSpacing(5)
        
        for i in range(36):
            row = i // 6
            col = i % 6
            btn = MotorButton(i)
            self.motor_buttons.append(btn)
            grid.addWidget(btn, row, col)
        
        layout.addLayout(grid)
        
        # Selection controls
        btn_layout = QHBoxLayout()
        
        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(self.select_all_motors)
        btn_layout.addWidget(select_all_btn)
        
        clear_all_btn = QPushButton("Clear All")
        clear_all_btn.clicked.connect(self.clear_all_motors)
        btn_layout.addWidget(clear_all_btn)
        
        layout.addLayout(btn_layout)
        
        group.setLayout(layout)
        return group
    
    def create_control_panel(self):
        """Create control panel."""
        group = QGroupBox("Experiment Control")
        layout = QVBoxLayout()
        
        # Duration
        layout.addWidget(QLabel("Duration (seconds):"))
        self.duration = QSpinBox()
        self.duration.setRange(1, 300)
        self.duration.setValue(10)
        layout.addWidget(self.duration)
        
        layout.addSpacing(20)
        
        # Status display
        layout.addWidget(QLabel("Status:"))
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("""
            QLabel {
                background-color: #e3f2fd;
                padding: 10px;
                border-radius: 5px;
                font-weight: bold;
            }
        """)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)
        
        layout.addSpacing(20)
        
        # Active motors count
        self.active_count_label = QLabel("Active Motors: 0")
        self.active_count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.active_count_label)
        
        layout.addStretch()
        
        # Start button
        self.start_btn = QPushButton("Start Experiment")
        self.start_btn.setMinimumHeight(50)
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 5px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        self.start_btn.clicked.connect(self.start_experiment)
        layout.addWidget(self.start_btn)
        
        # Stop button
        self.stop_btn = QPushButton("Stop Experiment")
        self.stop_btn.setMinimumHeight(50)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border: none;
                border-radius: 5px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #d32f2f;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        self.stop_btn.clicked.connect(self.stop_experiment)
        layout.addWidget(self.stop_btn)
        
        group.setLayout(layout)
        
        # Timer to update active count
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_active_count)
        self.update_timer.start(500)  # Update every 500ms
        
        return group
    
    def update_active_count(self):
        """Update the count of active motors."""
        count = sum(1 for btn in self.motor_buttons if btn.is_active)
        self.active_count_label.setText(f"Active Motors: {count}")
    
    def select_all_motors(self):
        """Select all motors."""
        for btn in self.motor_buttons:
            btn.setChecked(True)
            btn.is_active = True
            btn.update_style()
    
    def clear_all_motors(self):
        """Clear all motor selections."""
        for btn in self.motor_buttons:
            btn.setChecked(False)
            btn.is_active = False
            btn.update_style()
    
    def generate_fourier_coefficients(self):
        """Generate Fourier coefficients based on GUI settings."""
        signal_type = self.signal_type.currentText()
        amp_min = self.amp_min.value()
        amp_max = self.amp_max.value()
        period = self.period.value()
        n_terms = self.fourier_terms.value()
        
        # Validate amplitude range
        if amp_min >= amp_max:
            QMessageBox.warning(self, "Invalid Range", 
                              "Amplitude Min must be less than Amplitude Max!")
            return None
        
        # Calculate amplitude and DC offset
        amplitude = (amp_max - amp_min) / 2.0
        dc_offset = (amp_max + amp_min) / 2.0
        
        # Generate base coefficients
        if signal_type == "Sine Wave":
            coeffs = generate_sine_wave(
                n_motors=NUM_MOTORS,
                amplitude=amplitude,
                period=period,
                dc_offset=dc_offset,
                n_terms=n_terms
            )
        elif signal_type == "Square Wave":
            coeffs = generate_square_pulse(
                n_motors=NUM_MOTORS,
                amplitude=amp_max - amp_min,
                period=period,
                duty_cycle=0.5,
                n_terms=n_terms
            )
            # Add DC offset to square wave
            coeffs[:, 0] += amp_min
        else:  # Constant
            coeffs = generate_uniform(
                n_motors=NUM_MOTORS,
                value=dc_offset,
                n_terms=n_terms
            )
        
        # Zero out inactive motors (set them to minimum PWM)
        for i, btn in enumerate(self.motor_buttons):
            if not btn.is_active:
                # Set all coefficients to 0 except DC which maps to PWM_MIN
                coeffs[i, :] = 0.0
                coeffs[i, 0] = 0.0  # This will map to PWM_MIN in the flight loop
        
        return coeffs
    
    def start_experiment(self):
        """Start the experiment."""
        # Check if any motors are active
        active_count = sum(1 for btn in self.motor_buttons if btn.is_active)
        if active_count == 0:
            QMessageBox.warning(self, "No Motors Selected", 
                              "Please select at least one motor to activate!")
            return
        
        # Generate coefficients
        coeffs = self.generate_fourier_coefficients()
        if coeffs is None:
            return
        
        # Update UI
        self.experiment_running = True
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.status_label.setText("Running...")
        self.status_label.setStyleSheet("""
            QLabel {
                background-color: #c8e6c9;
                padding: 10px;
                border-radius: 5px;
                font-weight: bold;
                color: #2e7d32;
            }
        """)
        
        # Disable configuration during experiment
        self.signal_type.setEnabled(False)
        self.amp_min.setEnabled(False)
        self.amp_max.setEnabled(False)
        self.period.setEnabled(False)
        self.fourier_terms.setEnabled(False)
        for btn in self.motor_buttons:
            btn.setEnabled(False)
        
        # Start experiment in separate thread
        import threading
        experiment_thread = threading.Thread(
            target=self.run_experiment_thread,
            args=(coeffs,)
        )
        experiment_thread.daemon = True
        experiment_thread.start()
    
    def run_experiment_thread(self, coeffs):
        """Run the experiment (called in separate thread)."""
        try:
            duration = self.duration.value()
            amp_min = self.amp_min.value()
            amp_max = self.amp_max.value()
            
            # Run experiment directly without signal handling
            # (signal.signal only works in main thread)
            import platform
            import time
            from src.core import MotorStateBuffer
            from src.core.flight_loop import flight_loop
            from config import BASE_FREQUENCY
            
            self.stop_event = multiprocessing.Event()
            
            # Initialize shared memory
            self.shared_buffer = MotorStateBuffer(create=True)
            
            # Determine hardware mode
            use_mock = platform.system() == "Darwin"
            
            # Launch flight control process
            self.flight_process = multiprocessing.Process(
                target=flight_loop,
                args=(self.stop_event, use_mock, coeffs, BASE_FREQUENCY, None, 0.0, amp_min, amp_max, True),
                name="FlightLoop",
                daemon=False
            )
            self.flight_process.start()
            
            # Give flight process time to initialize
            time.sleep(0.5)
            
            # Run for specified duration (account for init time)
            start_time = time.perf_counter()
            while self.flight_process.is_alive():
                time.sleep(0.1)
                # Check if stop button was pressed
                if self.stop_event.is_set():
                    break
                # Check duration
                if time.perf_counter() - start_time >= duration:
                    self.stop_event.set()
                    break
            
            # Cleanup
            self.flight_process.join(timeout=2)
            if self.flight_process.is_alive():
                self.flight_process.terminate()
                self.flight_process.join()
            
            self.shared_buffer.unlink()
            
        except Exception as e:
            print(f"[GUI] Experiment error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Update UI when done
            QTimer.singleShot(0, self.experiment_finished)
    
    def experiment_finished(self):
        """Called when experiment finishes."""
        self.experiment_running = False
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_label.setText("Finished")
        self.status_label.setStyleSheet("""
            QLabel {
                background-color: #e3f2fd;
                padding: 10px;
                border-radius: 5px;
                font-weight: bold;
            }
        """)
        
        # Re-enable configuration
        self.signal_type.setEnabled(True)
        self.amp_min.setEnabled(True)
        self.amp_max.setEnabled(True)
        self.period.setEnabled(True)
        self.fourier_terms.setEnabled(True)
        for btn in self.motor_buttons:
            btn.setEnabled(True)
        
        QMessageBox.information(self, "Experiment Complete", 
                              "Experiment finished! Check the logs folder for data.")
    
    def stop_experiment(self):
        """Stop the running experiment immediately."""
        if self.experiment_running and self.stop_event:
            print("[GUI] Stop button pressed - stopping experiment...")
            self.stop_event.set()
            self.status_label.setText("Stopping...")
            self.status_label.setStyleSheet("""
                QLabel {
                    background-color: #fff9c4;
                    padding: 10px;
                    border-radius: 5px;
                    font-weight: bold;
                    color: #f57f17;
                }
            """)


def main_gui():
    """Main entry point for GUI."""
    # Set multiprocessing start method
    multiprocessing.set_start_method('fork', force=True)
    
    app = QApplication(sys.argv)
    app.setStyle('Fusion')  # Modern look
    
    # Set application font
    font = QFont("Arial", 10)
    app.setFont(font)
    
    window = WindWallGUI()
    window.show()
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main_gui()
