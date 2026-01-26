"""
GUI Dashboard using PyQt6 and pyqtgraph for real-time visualization and logging.
This is Process B, running in the main thread at 60 FPS.
"""

import sys
import time
import csv
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSlider, QSpinBox
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QFont
from multiprocessing import Process, Event
import pyqtgraph as pg

from config import NUM_MOTORS, GUI_UPDATE_RATE_FPS, LOG_INTERVAL_MS
from src.core import MotorStateBuffer
from src.core.flight_loop import flight_loop


class MotorDashboard(QMainWindow):
    """
    PyQt6 dashboard with real-time motor signal and PWM visualization.
    Updates at 60 FPS and logs data to CSV every 100ms.
    """
    
    def __init__(self):
        """Initialize the dashboard window and plots."""
        super().__init__()
        self.setWindowTitle("Active Wind Wall Control Dashboard")
        self.setGeometry(100, 100, 1400, 700)
        
        # Try to attach to shared memory
        try:
            self.shared_buffer = MotorStateBuffer(create=False)
            print("[Dashboard] Successfully attached to shared memory")
        except Exception as e:
            print(f"[Dashboard] ERROR: Could not attach to shared memory: {e}")
            print("[Dashboard] Make sure flight_loop process is running!")
            self.shared_buffer = None
        
        # Process management
        self.stop_event = Event()
        self.flight_process: Optional[Process] = None
        self.is_running = False
        
        # Setup logging
        self.log_dir = Path("logs")
        self.log_dir.mkdir(exist_ok=True)
        self.log_file: Optional[str] = None
        self.log_writer: Optional[csv.writer] = None
        self.last_log_time = time.perf_counter()
        
        # Signal parameters
        self.signal_amplitude = 1.0
        self.signal_frequency = 1.0
        
        # Data buffers for scrolling plots
        self.buffer_size = 1000
        self.pwm_history = np.zeros((self.buffer_size, NUM_MOTORS))
        self.signal_history = np.zeros((self.buffer_size, NUM_MOTORS))
        self.time_history = np.linspace(0, -2.5 * self.buffer_size, self.buffer_size)
        self.buffer_index = 0
        
        # Setup GUI
        self._setup_ui()
        
        # Setup update timer (16.67 ms for 60 FPS)
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._on_timer_tick)
        self.update_timer.start(int(1000 / GUI_UPDATE_RATE_FPS))
        
        self.frame_count = 0
    
    def _setup_ui(self) -> None:
        """Setup the UI with plots and labels."""
        # Main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout()
        
        # Configure pyqtgraph
        pg.setConfigOptions(antialias=True, background='w')
        
        # Control panel (top)
        control_layout = QHBoxLayout()
    
        # Start/Stop buttons
        self.start_button = QPushButton("▶ START")
        self.start_button.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 8px;")
        self.start_button.clicked.connect(self._on_start_clicked)
        self.start_button.setMinimumWidth(100)
    
        self.stop_button = QPushButton("⏹ STOP")
        self.stop_button.setStyleSheet("background-color: #f44336; color: white; font-weight: bold; padding: 8px;")
        self.stop_button.clicked.connect(self._on_stop_clicked)
        self.stop_button.setEnabled(False)
        self.stop_button.setMinimumWidth(100)
    
        control_layout.addWidget(QLabel("Control:"))
        control_layout.addWidget(self.start_button)
        control_layout.addWidget(self.stop_button)
    
        # Signal amplitude control
        control_layout.addSpacing(30)
        control_layout.addWidget(QLabel("Amplitude:"))
        self.amplitude_slider = QSlider(Qt.Orientation.Horizontal)
        self.amplitude_slider.setMinimum(0)
        self.amplitude_slider.setMaximum(100)
        self.amplitude_slider.setValue(100)
        self.amplitude_slider.setMaximumWidth(150)
        self.amplitude_slider.valueChanged.connect(self._on_amplitude_changed)
        self.amplitude_label = QLabel("1.0")
        self.amplitude_label.setMinimumWidth(40)
        control_layout.addWidget(self.amplitude_slider)
        control_layout.addWidget(self.amplitude_label)
    
        # Signal frequency control
        control_layout.addSpacing(30)
        control_layout.addWidget(QLabel("Frequency:"))
        self.frequency_spinbox = QSpinBox()
        self.frequency_spinbox.setMinimum(1)
        self.frequency_spinbox.setMaximum(20)
        self.frequency_spinbox.setValue(1)
        self.frequency_spinbox.setMaximumWidth(60)
        self.frequency_spinbox.valueChanged.connect(self._on_frequency_changed)
        control_layout.addWidget(self.frequency_spinbox)
        control_layout.addWidget(QLabel("Hz"))
    
        control_layout.addStretch()
        layout.addLayout(control_layout)
        
        # Top plot: Input Signal
        self.signal_plot = pg.PlotWidget()
        self.signal_plot.setLabel('left', 'Signal', units='')
        self.signal_plot.setLabel('bottom', 'Time', units='s')
        self.signal_plot.setTitle("Physics Signal (Fourier Synthesis)")
        self.signal_plot.setYRange(0, 1.0)
        self.signal_curve_avg = self.signal_plot.plot(
            self.time_history, np.zeros(self.buffer_size),
            pen=pg.mkPen(color=(0, 0, 255), width=2),
            name="Avg Signal"
        )
        
        # Bottom plot: Actual PWM
        self.pwm_plot = pg.PlotWidget()
        self.pwm_plot.setLabel('left', 'PWM', units='µs')
        self.pwm_plot.setLabel('bottom', 'Time', units='s')
        self.pwm_plot.setTitle("Actual PWM (After Safety Checks)")
        self.pwm_plot.setYRange(900, 2100)
        self.pwm_curve_avg = self.pwm_plot.plot(
            self.time_history, np.zeros(self.buffer_size),
            pen=pg.mkPen(color=(255, 0, 0), width=2),
            name="Avg PWM"
        )
        
        # Status label
        self.status_label = QLabel("Waiting for flight_loop process...")
        self.status_label.setFont(QFont("Courier", 10))
        
        # Add to layout
        layout.addWidget(QLabel("Signal Output (0.0-1.0)"))
        layout.addWidget(self.signal_plot, 1)
        layout.addWidget(QLabel("Motor PWM Commands (1000-2000 µs)"))
        layout.addWidget(self.pwm_plot, 1)
        layout.addWidget(self.status_label)
        
        main_widget.setLayout(layout)
    
    def _init_log_file(self) -> None:
        """Initialize a new CSV log file with timestamp."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = str(self.log_dir / f"flight_log_{timestamp}.csv")
        
        with open(self.log_file, 'w', newline='') as f:
            self.log_writer = csv.writer(f)
            # Write header
            header = ['timestamp'] + [f'pwm_{i}' for i in range(NUM_MOTORS)] + \
                     [f'rpm_{i}' for i in range(NUM_MOTORS)]
            self.log_writer.writerow(header)
        
        print(f"[Dashboard] Log file created: {self.log_file}")
    
    def _on_start_clicked(self) -> None:
        """Handle Start button click."""
        if self.is_running:
            return
        
        print("[Dashboard] Starting flight_loop process...")
        self.stop_event.clear()
        
        try:
            # Initialize shared memory if needed
            if self.shared_buffer is None:
                self.shared_buffer = MotorStateBuffer(create=True)
                print("[Dashboard] Created shared memory buffer")
            else:
                # Attach to existing buffer
                self.shared_buffer = MotorStateBuffer(create=False)
        except Exception as e:
            print(f"[Dashboard] ERROR: Could not setup shared memory: {e}")
            return
        
        # Launch flight control process
        self.flight_process = Process(
            target=flight_loop,
            args=(self.stop_event, True),  # use_mock=True for now
            name="FlightLoop",
            daemon=False
        )
        self.flight_process.start()
        
        self.is_running = True
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.status_label.setText("Status: RUNNING")
        print("[Dashboard] Flight process started")
    
    def _on_stop_clicked(self) -> None:
        """Handle Stop button click."""
        if not self.is_running or self.flight_process is None:
            return
        
        print("[Dashboard] Stopping flight_loop process...")
        self.stop_event.set()
        
        # Wait for process to finish
        self.flight_process.join(timeout=2)
        if self.flight_process.is_alive():
            print("[Dashboard] Force-terminating flight_process...")
            self.flight_process.terminate()
            self.flight_process.join()
        
        self.is_running = False
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.status_label.setText("Status: STOPPED")
        print("[Dashboard] Flight process stopped")
    
    def _on_amplitude_changed(self, value: int) -> None:
        """Handle amplitude slider change."""
        self.signal_amplitude = value / 100.0
        self.amplitude_label.setText(f"{self.signal_amplitude:.2f}")
        print(f"[Dashboard] Amplitude changed to {self.signal_amplitude:.2f}")
    
    def _on_frequency_changed(self, value: int) -> None:
        """Handle frequency spinbox change."""
        self.signal_frequency = float(value)
        print(f"[Dashboard] Frequency changed to {self.signal_frequency} Hz")
    
    def _on_timer_tick(self) -> None:
        """Called on each timer tick (60 FPS)."""
        if self.shared_buffer is None:
            self.status_label.setText("ERROR: No shared memory connection")
        
            if not self.is_running:
                self.status_label.setText("Status: Waiting to start...")
                return
            return
        
        self.frame_count += 1
        
        try:
            # Read current state from shared memory
            all_data = self.shared_buffer.get_all()
            pwm_current = all_data[:, 0]
            rpm_current = all_data[:, 1]
            
            # Approximate signal from PWM (inverse map)
            signal_current = (pwm_current - 1000) / 1000.0
            signal_current = np.clip(signal_current, 0.0, 1.0)
            
            # Update circular buffer
            idx = self.buffer_index % self.buffer_size
            self.pwm_history[idx, :] = pwm_current
            self.signal_history[idx, :] = signal_current
            self.buffer_index += 1
            
            # Update plots with rolling average
            pwm_avg = self.pwm_history.mean(axis=1)
            signal_avg = self.signal_history.mean(axis=1)
            
            self.pwm_curve_avg.setData(self.time_history, pwm_avg)
            self.signal_curve_avg.setData(self.time_history, signal_avg)
            
            # Update status
            if self.frame_count % 60 == 0:  # Update status every 1 second
                avg_pwm = pwm_current.mean()
                avg_rpm = rpm_current.mean()
                self.status_label.setText(
                    f"Frame: {self.frame_count:6d} | "
                    f"Avg PWM: {avg_pwm:.0f} µs | "
                    f"Avg RPM: {avg_rpm:.1f} | "
                    f"Data logged to: {self.log_file or 'pending'}"
                )
            
            # Logging at specified interval
            current_time = time.perf_counter()
            if current_time - self.last_log_time >= (LOG_INTERVAL_MS / 1000.0):
                if self.log_file is None:
                    self._init_log_file()
                
                # Append data to CSV
                with open(self.log_file, 'a', newline='') as f:
                    writer = csv.writer(f)
                    row = [datetime.now().isoformat()] + pwm_current.tolist() + rpm_current.tolist()
                    writer.writerow(row)
                
                self.last_log_time = current_time
        
        except Exception as e:
            self.status_label.setText(f"ERROR: {e}")
            print(f"[Dashboard] Error in timer tick: {e}")
    
    def closeEvent(self, event) -> None:
        """Handle window close event."""
        print("[Dashboard] Closing...")
        self.update_timer.stop()
        if self.shared_buffer:
            self.shared_buffer.close()
        event.accept()
        
        # Stop process if running
        if self.is_running:
            self._on_stop_clicked()


def launch_dashboard() -> None:
    """
    Launch the PyQt6 dashboard application.
    This is the main GUI process (Process B).
    """
    app = QApplication(sys.argv)
    window = MotorDashboard()
    window.show()
    sys.exit(app.exec())
