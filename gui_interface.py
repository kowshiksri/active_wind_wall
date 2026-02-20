#!/usr/bin/env python3
"""
Enhanced GUI Interface for Active Wind Wall Control System.
Features: Multiple groups, live monitoring, custom Fourier signals.
"""

import sys
import numpy as np
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox, QSpinBox, QDoubleSpinBox,
    QGridLayout, QGroupBox, QMessageBox, QListWidget, QSplitter,
    QTableWidget, QTableWidgetItem, QHeaderView
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QColor
import pyqtgraph as pg
import multiprocessing
from collections import deque

from config import BASE_FREQUENCY, NUM_MOTORS, PWM_MIN, PWM_MAX
from src.physics.signal_designer import generate_sine_wave, generate_square_pulse, generate_uniform
from src.core import MotorStateBuffer


# Color palette for groups
GROUP_COLORS = [
    ("#4CAF50", "#2E7D32"),  # Green
    ("#2196F3", "#1565C0"),  # Blue
    ("#F44336", "#C62828"),  # Red
    ("#FF9800", "#E65100"),  # Orange
    ("#9C27B0", "#6A1B9A"),  # Purple
    ("#00BCD4", "#006064"),  # Cyan
]


class MotorGroup:
    """Represents a group of motors with shared signal configuration."""
    
    def __init__(self, name, color_index=0):
        self.name = name
        self.color_index = color_index
        self.motors = set()  # Set of motor IDs
        
        # Signal configuration
        self.signal_type = "Sine Wave"
        self.amp_min = 0.25
        self.amp_max = 0.75
        self.dc_value = 0.5  # For Constant DC mode
        self.period = 2.0
        self.phase_offset = 0.0  # Phase shift in seconds (for time-shifted on/off)
        self.fourier_terms = 7
        
        # Custom Fourier harmonics: [(harmonic_num, amplitude, phase_deg), ...]
        self.custom_harmonics = []
    
    def get_color(self):
        """Get the color tuple for this group."""
        return GROUP_COLORS[self.color_index % len(GROUP_COLORS)]


class MotorButton(QPushButton):
    """Custom button for motor selection with group support."""
    
    def __init__(self, motor_id, parent_gui):
        super().__init__(str(motor_id))
        self.motor_id = motor_id
        self.parent_gui = parent_gui
        self.assigned_group = None
        self.setMinimumSize(60, 60)
        self.setMaximumSize(60, 60)
        self.update_style()
        self.clicked.connect(self.on_click)
    
    def on_click(self):
        """Handle motor button click - assign to selected group."""
        selected_group = self.parent_gui.get_selected_group()
        if selected_group:
            if self.assigned_group == selected_group:
                # Unassign if already in this group
                selected_group.motors.discard(self.motor_id)
                self.assigned_group = None
            else:
                # Remove from old group if assigned
                if self.assigned_group:
                    self.assigned_group.motors.discard(self.motor_id)
                # Assign to new group
                selected_group.motors.add(self.motor_id)
                self.assigned_group = selected_group
            self.update_style()
    
    def update_style(self):
        """Update button appearance based on group assignment."""
        if self.assigned_group:
            bg_color, border_color = self.assigned_group.get_color()
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {bg_color};
                    color: white;
                    border: 3px solid {border_color};
                    border-radius: 8px;
                    font-weight: bold;
                    font-size: 14px;
                }}
                QPushButton:hover {{
                    border: 3px solid #FFD700;
                }}
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
        self.groups = []
        self.selected_group_index = -1
        self.motor_buttons = []
        self.experiment_running = False
        self.flight_process = None
        self.stop_event = None
        self.shared_buffer = None
        
        # Live monitoring - oscilloscope style
        self.monitor_data_time = deque(maxlen=200)  # 5 seconds at 40Hz
        self.monitor_data_pwm = deque(maxlen=200)
        self.monitor_timer = None
        self.experiment_start_time = None  # Set when experiment starts - never resets
        
        self.init_ui()
        
        # Create default group after UI is initialized
        self.add_group("Group 1")
    
    def init_ui(self):
        """Initialize the user interface."""
        self.setWindowTitle("Active Wind Wall Control Interface - Enhanced")
        self.setGeometry(50, 50, 1400, 900)
        
        # Central widget with splitter
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Top section - Configuration and Grid
        top_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left panel - Groups and signal configuration
        left_panel = self.create_left_panel()
        top_splitter.addWidget(left_panel)
        
        # Center panel - Motor grid
        grid_panel = self.create_grid_panel()
        top_splitter.addWidget(grid_panel)
        
        # Right panel - Controls
        control_panel = self.create_control_panel()
        top_splitter.addWidget(control_panel)
        
        top_splitter.setStretchFactor(0, 1)
        top_splitter.setStretchFactor(1, 2)
        top_splitter.setStretchFactor(2, 1)
        
        main_layout.addWidget(top_splitter, stretch=2)
        
        # Bottom section - Live monitoring
        monitor_panel = self.create_monitor_panel()
        main_layout.addWidget(monitor_panel, stretch=1)
    
    def create_left_panel(self):
        """Create groups and signal configuration panel."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Groups section
        groups_box = QGroupBox("Motor Groups")
        groups_layout = QVBoxLayout()
        
        self.groups_list = QListWidget()
        self.groups_list.currentRowChanged.connect(self.on_group_selected)
        groups_layout.addWidget(self.groups_list)
        
        # Group buttons
        group_btn_layout = QHBoxLayout()
        add_group_btn = QPushButton("Add Group")
        add_group_btn.clicked.connect(self.add_group_clicked)
        delete_group_btn = QPushButton("Delete Group")
        delete_group_btn.clicked.connect(self.delete_group_clicked)
        group_btn_layout.addWidget(add_group_btn)
        group_btn_layout.addWidget(delete_group_btn)
        groups_layout.addLayout(group_btn_layout)
        
        groups_box.setLayout(groups_layout)
        layout.addWidget(groups_box)
        
        # Signal configuration
        config_box = QGroupBox("Signal Configuration")
        config_layout = QVBoxLayout()
        
        self.selected_group_label = QLabel("Selected: None")
        self.selected_group_label.setStyleSheet("font-weight: bold; color: #2196F3;")
        config_layout.addWidget(self.selected_group_label)
        
        config_layout.addWidget(QLabel("Signal Type:"))
        self.signal_type = QComboBox()
        self.signal_type.addItems(["Sine Wave", "Square Wave", "Constant DC", "Custom Fourier"])
        self.signal_type.currentTextChanged.connect(self.on_signal_type_changed)
        config_layout.addWidget(self.signal_type)
        
        # Standard signal parameters
        self.standard_params_widget = QWidget()
        standard_layout = QVBoxLayout(self.standard_params_widget)
        standard_layout.setContentsMargins(0, 0, 0, 0)
        
        standard_layout.addWidget(QLabel("Amplitude Min:"))
        self.amp_min = QDoubleSpinBox()
        self.amp_min.setRange(0.0, 1.0)
        self.amp_min.setSingleStep(0.05)
        self.amp_min.setValue(0.25)
        self.amp_min.setDecimals(2)
        self.amp_min.valueChanged.connect(self.on_param_changed)
        standard_layout.addWidget(self.amp_min)
        
        standard_layout.addWidget(QLabel("Amplitude Max:"))
        self.amp_max = QDoubleSpinBox()
        self.amp_max.setRange(0.0, 1.0)
        self.amp_max.setSingleStep(0.05)
        self.amp_max.setValue(0.75)
        self.amp_max.setDecimals(2)
        self.amp_max.valueChanged.connect(self.on_param_changed)
        standard_layout.addWidget(self.amp_max)
        
        standard_layout.addWidget(QLabel("Period (s):"))
        self.period = QDoubleSpinBox()
        self.period.setRange(0.1, 60.0)
        self.period.setSingleStep(0.5)
        self.period.setValue(2.0)
        self.period.setDecimals(1)
        self.period.valueChanged.connect(self.on_param_changed)
        standard_layout.addWidget(self.period)
        
        standard_layout.addWidget(QLabel("Fourier Terms:"))
        self.fourier_terms = QSpinBox()
        self.fourier_terms.setRange(1, 20)
        self.fourier_terms.setValue(7)
        self.fourier_terms.valueChanged.connect(self.on_param_changed)
        standard_layout.addWidget(self.fourier_terms)
        
        config_layout.addWidget(self.standard_params_widget)
        
        # DC Constant value widget (only for Constant DC)
        self.dc_params_widget = QWidget()
        dc_layout = QVBoxLayout(self.dc_params_widget)
        dc_layout.setContentsMargins(0, 0, 0, 0)
        
        dc_layout.addWidget(QLabel("DC Value:"))
        self.dc_value_spinbox = QDoubleSpinBox()
        self.dc_value_spinbox.setRange(0.0, 1.0)
        self.dc_value_spinbox.setSingleStep(0.05)
        self.dc_value_spinbox.setValue(0.5)
        self.dc_value_spinbox.setDecimals(2)
        self.dc_value_spinbox.valueChanged.connect(self.on_dc_value_changed)
        dc_layout.addWidget(self.dc_value_spinbox)
        
        dc_layout.addWidget(QLabel("Phase Offset (s):"))
        self.phase_offset_spinbox = QDoubleSpinBox()
        self.phase_offset_spinbox.setRange(-30.0, 30.0)
        self.phase_offset_spinbox.setSingleStep(0.1)
        self.phase_offset_spinbox.setValue(0.0)
        self.phase_offset_spinbox.setDecimals(1)
        self.phase_offset_spinbox.setToolTip("Time shift for square/sine waves (for synchronized on/off groups)")
        self.phase_offset_spinbox.valueChanged.connect(self.on_param_changed)
        dc_layout.addWidget(self.phase_offset_spinbox)
        
        config_layout.addWidget(self.dc_params_widget)
        self.dc_params_widget.hide()
        
        # Phase offset also for standard signals
        self.phase_offset_label = QLabel("Phase Offset (s):")
        self.phase_offset_label.hide()
        config_layout.addWidget(self.phase_offset_label)
        self.phase_offset_for_standard = QDoubleSpinBox()
        self.phase_offset_for_standard.setRange(-30.0, 30.0)
        self.phase_offset_for_standard.setSingleStep(0.1)
        self.phase_offset_for_standard.setValue(0.0)
        self.phase_offset_for_standard.setDecimals(1)
        self.phase_offset_for_standard.setToolTip("Time shift for synchronized on/off groups")
        self.phase_offset_for_standard.valueChanged.connect(self.on_param_changed)
        self.phase_offset_for_standard.hide()
        config_layout.addWidget(self.phase_offset_for_standard)
        
        # Custom Fourier parameters
        self.custom_params_widget = QWidget()
        custom_layout = QVBoxLayout(self.custom_params_widget)
        custom_layout.setContentsMargins(0, 0, 0, 0)
        
        custom_layout.addWidget(QLabel("Harmonics:"))
        self.harmonics_table = QTableWidget()
        self.harmonics_table.setColumnCount(3)
        self.harmonics_table.setHorizontalHeaderLabels(["#", "Amplitude", "Phase (°)"])
        self.harmonics_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.harmonics_table.setMaximumHeight(150)
        custom_layout.addWidget(self.harmonics_table)
        
        harmonic_btn_layout = QHBoxLayout()
        add_harmonic_btn = QPushButton("Add Harmonic")
        add_harmonic_btn.clicked.connect(self.add_harmonic)
        remove_harmonic_btn = QPushButton("Remove")
        remove_harmonic_btn.clicked.connect(self.remove_harmonic)
        harmonic_btn_layout.addWidget(add_harmonic_btn)
        harmonic_btn_layout.addWidget(remove_harmonic_btn)
        custom_layout.addLayout(harmonic_btn_layout)
        
        config_layout.addWidget(self.custom_params_widget)
        self.custom_params_widget.hide()
        
        config_box.setLayout(config_layout)
        layout.addWidget(config_box)
        
        layout.addStretch()
        
        return widget
    
    def create_grid_panel(self):
        """Create motor grid panel."""
        group = QGroupBox("Motor Grid (6×6)")
        layout = QVBoxLayout()
        
        info_label = QLabel("Click motors to assign to selected group")
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_label.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(info_label)
        
        grid = QGridLayout()
        grid.setSpacing(5)
        
        for i in range(36):
            row = i // 6
            col = i % 6
            btn = MotorButton(i, self)
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
        """Create experiment control panel."""
        group = QGroupBox("Experiment Control")
        layout = QVBoxLayout()
        
        layout.addWidget(QLabel("Duration (seconds):"))
        self.duration = QSpinBox()
        self.duration.setRange(1, 300)
        self.duration.setValue(10)
        layout.addWidget(self.duration)
        
        layout.addSpacing(10)
        
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
        
        layout.addSpacing(10)
        
        self.active_count_label = QLabel("Active Motors: 0")
        self.active_count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.active_count_label)
        
        layout.addStretch()
        
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
        self.update_timer.start(500)
        
        return group
    
    def create_monitor_panel(self):
        """Create live monitoring panel."""
        group = QGroupBox("Live Monitor")
        layout = QVBoxLayout()
        
        # Monitor type and selection
        control_layout = QHBoxLayout()
        control_layout.addWidget(QLabel("Monitor:"))
        
        self.monitor_type = QComboBox()
        self.monitor_type.addItem("Individual Motor")
        self.monitor_type.addItem("Group Average")
        self.monitor_type.currentTextChanged.connect(self.on_monitor_type_changed)
        control_layout.addWidget(self.monitor_type)
        
        self.monitor_motor_select = QComboBox()
        for i in range(36):
            self.monitor_motor_select.addItem(f"Motor {i}")
        self.monitor_motor_select.currentIndexChanged.connect(self.on_monitor_selection_changed)
        control_layout.addWidget(self.monitor_motor_select)
        
        self.monitor_group_select = QComboBox()
        self.monitor_group_select.currentIndexChanged.connect(self.on_monitor_selection_changed)
        self.monitor_group_select.hide()
        control_layout.addWidget(self.monitor_group_select)
        
        control_layout.addStretch()
        layout.addLayout(control_layout)
        
        # Plot widget
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('w')
        self.plot_widget.setLabel('left', 'PWM Value', units='μs')
        self.plot_widget.setLabel('bottom', 'Time', units='s')
        self.plot_widget.setYRange(900, 2100)
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_curve = self.plot_widget.plot(pen=pg.mkPen(color='b', width=2))
        layout.addWidget(self.plot_widget)
        
        group.setLayout(layout)
        return group
    
    def add_group(self, name=None):
        """Add a new motor group."""
        if name is None:
            name = f"Group {len(self.groups) + 1}"
        group = MotorGroup(name, len(self.groups))
        self.groups.append(group)
        self.groups_list.addItem(name)
        self.update_monitor_group_list()
        if len(self.groups) == 1:
            self.groups_list.setCurrentRow(0)
        return group
    
    def add_group_clicked(self):
        """Handle add group button click."""
        self.add_group()
    
    def delete_group_clicked(self):
        """Handle delete group button click."""
        if self.selected_group_index >= 0 and len(self.groups) > 1:
            group = self.groups[self.selected_group_index]
            # Unassign motors from this group
            for btn in self.motor_buttons:
                if btn.assigned_group == group:
                    btn.assigned_group = None
                    btn.update_style()
            # Remove group
            self.groups.pop(self.selected_group_index)
            self.groups_list.takeItem(self.selected_group_index)
            self.update_monitor_group_list()
        elif len(self.groups) == 1:
            QMessageBox.warning(self, "Cannot Delete", "At least one group must exist!")
    
    def on_group_selected(self, index):
        """Handle group selection change."""
        self.selected_group_index = index
        if index >= 0 and index < len(self.groups):
            group = self.groups[index]
            self.selected_group_label.setText(f"Selected: {group.name}")
            bg_color, _ = group.get_color()
            self.selected_group_label.setStyleSheet(f"font-weight: bold; color: {bg_color};")
            
            # Block signals while loading group parameters to prevent on_param_changed
            # from being triggered with partially-updated spinbox values
            self.signal_type.blockSignals(True)
            self.amp_min.blockSignals(True)
            self.amp_max.blockSignals(True)
            self.dc_value_spinbox.blockSignals(True)
            self.period.blockSignals(True)
            self.phase_offset_for_standard.blockSignals(True)
            self.phase_offset_spinbox.blockSignals(True)
            self.fourier_terms.blockSignals(True)
            
            try:
                # Load group's signal configuration
                self.signal_type.setCurrentText(group.signal_type)
                self.amp_min.setValue(group.amp_min)
                self.amp_max.setValue(group.amp_max)
                self.dc_value_spinbox.setValue(group.dc_value)
                self.period.setValue(group.period)
                self.phase_offset_for_standard.setValue(group.phase_offset)
                self.phase_offset_spinbox.setValue(group.phase_offset)
                self.fourier_terms.setValue(group.fourier_terms)
                self.load_custom_harmonics(group)
            finally:
                # Always unblock signals, even if an exception occurs
                self.signal_type.blockSignals(False)
                self.amp_min.blockSignals(False)
                self.amp_max.blockSignals(False)
                self.dc_value_spinbox.blockSignals(False)
                self.period.blockSignals(False)
                self.phase_offset_for_standard.blockSignals(False)
                self.phase_offset_spinbox.blockSignals(False)
                self.fourier_terms.blockSignals(False)
    
    def on_signal_type_changed(self, signal_type):
        """Handle signal type change - show/hide controls dynamically."""
        is_sine = signal_type == "Sine Wave"
        is_square = signal_type == "Square Wave"
        is_custom = signal_type == "Custom Fourier"
        is_constant = signal_type == "Constant DC"
        
        # Show standard params for sine/square (hide for constant/custom)
        self.standard_params_widget.setVisible(is_sine or is_square)
        
        # Show DC params only for constant
        self.dc_params_widget.setVisible(is_constant)
        
        # Show custom params only for custom
        self.custom_params_widget.setVisible(is_custom)
        
        # Show phase offset for sine, square, and constant
        self.phase_offset_label.setVisible(is_sine or is_square or is_constant)
        self.phase_offset_for_standard.setVisible(is_sine or is_square)
        self.phase_offset_spinbox.setVisible(is_constant)
        
        if self.selected_group_index >= 0:
            self.groups[self.selected_group_index].signal_type = signal_type
    
    def on_dc_value_changed(self):
        """Handle DC value change."""
        if self.selected_group_index >= 0:
            self.groups[self.selected_group_index].dc_value = self.dc_value_spinbox.value()
    
    def on_param_changed(self):
        """Handle parameter change."""
        if self.selected_group_index >= 0:
            group = self.groups[self.selected_group_index]
            group.amp_min = self.amp_min.value()
            group.amp_max = self.amp_max.value()
            group.period = self.period.value()
            group.fourier_terms = self.fourier_terms.value()
            # Save phase offset from whichever spinbox is visible
            if self.phase_offset_for_standard.isVisible():
                group.phase_offset = self.phase_offset_for_standard.value()
            elif self.phase_offset_spinbox.isVisible():
                group.phase_offset = self.phase_offset_spinbox.value()
    
    def add_harmonic(self):
        """Add a new harmonic to custom Fourier."""
        row = self.harmonics_table.rowCount()
        self.harmonics_table.insertRow(row)
        self.harmonics_table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
        self.harmonics_table.setItem(row, 1, QTableWidgetItem("0.1"))
        self.harmonics_table.setItem(row, 2, QTableWidgetItem("0"))
        self.save_custom_harmonics()
    
    def remove_harmonic(self):
        """Remove selected harmonic."""
        current_row = self.harmonics_table.currentRow()
        if current_row >= 0:
            self.harmonics_table.removeRow(current_row)
            # Renumber harmonics
            for i in range(self.harmonics_table.rowCount()):
                self.harmonics_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self.save_custom_harmonics()
    
    def load_custom_harmonics(self, group):
        """Load custom harmonics from group."""
        self.harmonics_table.setRowCount(0)
        for harmonic_num, amplitude, phase_deg in group.custom_harmonics:
            row = self.harmonics_table.rowCount()
            self.harmonics_table.insertRow(row)
            self.harmonics_table.setItem(row, 0, QTableWidgetItem(str(harmonic_num)))
            self.harmonics_table.setItem(row, 1, QTableWidgetItem(str(amplitude)))
            self.harmonics_table.setItem(row, 2, QTableWidgetItem(str(phase_deg)))
    
    def save_custom_harmonics(self):
        """Save custom harmonics to current group."""
        if self.selected_group_index >= 0:
            group = self.groups[self.selected_group_index]
            group.custom_harmonics = []
            for i in range(self.harmonics_table.rowCount()):
                try:
                    harmonic_num = int(self.harmonics_table.item(i, 0).text())
                    amplitude = float(self.harmonics_table.item(i, 1).text())
                    phase_deg = float(self.harmonics_table.item(i, 2).text())
                    group.custom_harmonics.append((harmonic_num, amplitude, phase_deg))
                except (ValueError, AttributeError):
                    pass
    
    def on_monitor_type_changed(self, monitor_type):
        """Handle monitor type change."""
        if monitor_type == "Individual Motor":
            self.monitor_motor_select.show()
            self.monitor_group_select.hide()
        else:
            self.monitor_motor_select.hide()
            self.monitor_group_select.show()
        # Clear data when switching monitor type
        self.clear_monitor_data()
    
    def on_monitor_selection_changed(self):
        """Handle motor/group selection change - clear plot for fresh start."""
        self.clear_monitor_data()
    
    def clear_monitor_data(self):
        """Clear monitoring display data (don't reset experiment_start_time)."""
        self.monitor_data_time.clear()
        self.monitor_data_pwm.clear()
        # NOTE: experiment_start_time persists across selections - it's the reference point!
        self.plot_curve.setData([], [])
    
    def update_monitor_group_list(self):
        """Update the monitor group dropdown."""
        self.monitor_group_select.clear()
        for group in self.groups:
            self.monitor_group_select.addItem(group.name)
    
    def get_selected_group(self):
        """Get the currently selected group."""
        if 0 <= self.selected_group_index < len(self.groups):
            return self.groups[self.selected_group_index]
        return None
    
    def select_all_motors(self):
        """Assign all motors to the currently selected group."""
        selected_group = self.get_selected_group()
        if selected_group:
            for btn in self.motor_buttons:
                # Remove from old group if assigned
                if btn.assigned_group and btn.assigned_group != selected_group:
                    btn.assigned_group.motors.discard(btn.motor_id)
                # Assign to selected group
                selected_group.motors.add(btn.motor_id)
                btn.assigned_group = selected_group
                btn.update_style()
        else:
            QMessageBox.warning(self, "No Group Selected", "Please select a group first!")
    
    def clear_all_motors(self):
        """Clear all motor assignments."""
        for btn in self.motor_buttons:
            if btn.assigned_group:
                btn.assigned_group.motors.discard(btn.motor_id)
            btn.assigned_group = None
            btn.update_style()
    
    def update_active_count(self):
        """Update the count of active motors."""
        count = sum(1 for btn in self.motor_buttons if btn.assigned_group is not None)
        self.active_count_label.setText(f"Active Motors: {count}")
    
    def generate_group_coefficients(self, group):
        """Generate Fourier coefficients for a specific group."""
        signal_type = group.signal_type
        amp_min = group.amp_min
        amp_max = group.amp_max
        dc_value = group.dc_value
        period = group.period
        n_terms = group.fourier_terms
        phase_offset = group.phase_offset
        
        # CRITICAL: Calculate base_freq from period (1/period)
        # This ensures the signal reconstruction uses the correct frequency
        base_freq = 1.0 / period if period > 0 else BASE_FREQUENCY
        
        if signal_type == "Custom Fourier":
            # Generate from custom harmonics
            coeffs = np.zeros((NUM_MOTORS, n_terms))
            for harmonic_num, amplitude, phase_deg in group.custom_harmonics:
                if 0 <= harmonic_num < n_terms:
                    coeffs[:, harmonic_num] = amplitude
                    # Phase will be handled separately if needed
            return coeffs
        
        # Calculate amplitude and DC offset
        amplitude = (amp_max - amp_min) / 2.0
        dc_offset = (amp_max + amp_min) / 2.0
        
        if signal_type == "Sine Wave":
            coeffs = generate_sine_wave(
                n_motors=NUM_MOTORS,
                amplitude=amplitude,
                period=period,
                dc_offset=dc_offset,
                n_terms=n_terms,
                base_freq=base_freq
            )
        elif signal_type == "Square Wave":
            # For square wave between amp_min and amp_max:
            # - Pass HALF the range as amplitude (harmonics swing ±amplitude around DC)
            # - Set DC to midpoint
            amplitude_half_range = (amp_max - amp_min) / 2.0
            coeffs = generate_square_pulse(
                n_motors=NUM_MOTORS,
                amplitude=amplitude_half_range,
                period=period,
                duty_cycle=0.5,
                n_terms=n_terms,
                base_freq=base_freq
            )
            # Correct the DC offset to be the midpoint between min and max
            coeffs[:, 0] = dc_offset  # (amp_max + amp_min) / 2.0
        else:  # Constant DC
            coeffs = generate_uniform(
                n_motors=NUM_MOTORS,
                value=dc_value,
                n_terms=n_terms
            )
        
        return coeffs
    
    def generate_fourier_coefficients(self):
        """Generate combined Fourier coefficients and per-motor omega values."""
        # Determine max number of terms needed
        max_terms = max((g.fourier_terms for g in self.groups), default=7)
        
        # Initialize coefficient matrix and omega array (rad/s per motor)
        final_coeffs = np.zeros((NUM_MOTORS, max_terms))
        omega_per_motor = np.full(NUM_MOTORS, 2.0 * np.pi * BASE_FREQUENCY, dtype=float)
        
        # Process each group
        for group in self.groups:
            if len(group.motors) == 0:
                continue
            
            group_coeffs = self.generate_group_coefficients(group)
            group_omega = 2.0 * np.pi * (1.0 / group.period) if group.period > 0 else 2.0 * np.pi * BASE_FREQUENCY
            
            # Assign coefficients and omega to motors in this group
            for motor_id in group.motors:
                # Pad or truncate to match final size
                terms_to_copy = min(group_coeffs.shape[1], max_terms)
                final_coeffs[motor_id, :terms_to_copy] = group_coeffs[motor_id, :terms_to_copy]
                omega_per_motor[motor_id] = group_omega
        
        # Motors not in any group get zero coefficients (PWM_MIN); omega left at default
        for i, btn in enumerate(self.motor_buttons):
            if btn.assigned_group is None:
                final_coeffs[i, :] = 0.0
        
        return final_coeffs, omega_per_motor
    
    def start_experiment(self):
        """Start the experiment."""
        # Check if any motors are assigned
        active_count = sum(1 for btn in self.motor_buttons if btn.assigned_group is not None)
        if active_count == 0:
            QMessageBox.warning(self, "No Motors Assigned", 
                              "Please assign at least one motor to a group!")
            return
        
        # Reset experiment timeline for fresh start
        self.experiment_start_time = None
        
        # Generate coefficients and per-motor omega
        coeffs, omega_per_motor = self.generate_fourier_coefficients()
        
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
        self.groups_list.setEnabled(False)
        self.signal_type.setEnabled(False)
        for btn in self.motor_buttons:
            btn.setEnabled(False)
        
        # Start live monitoring
        self.start_live_monitor()
        
        # Start experiment in separate thread
        import threading
        experiment_thread = threading.Thread(
            target=self.run_experiment_thread,
            args=(coeffs, omega_per_motor)
        )
        experiment_thread.daemon = True
        experiment_thread.start()
    
    def run_experiment_thread(self, coeffs, omega_per_motor):
        """Run the experiment (called in separate thread)."""
        try:
            duration = self.duration.value()
            
            import platform
            import time
            from src.core.flight_loop import flight_loop
            from config import BASE_FREQUENCY

            # If any group uses Square Wave, loosen slew limit to avoid edge smoothing
            from config import PWM_MAX, PWM_MIN, SLEW_LIMIT
            square_wave_present = any(g.signal_type == "Square Wave" and len(g.motors) > 0 for g in self.groups)
            slew_limit_override = (PWM_MAX - PWM_MIN) if square_wave_present else SLEW_LIMIT
            
            self.stop_event = multiprocessing.Event()
            self.shared_buffer = MotorStateBuffer(create=True)
            
            use_mock = platform.system() == "Darwin"
            
            self.flight_process = multiprocessing.Process(
                target=flight_loop,
                args=(self.stop_event, use_mock, coeffs, BASE_FREQUENCY, omega_per_motor, None, 0.0, 0.0, 1.0, True, 40, slew_limit_override),
                name="FlightLoop",
                daemon=False
            )
            self.flight_process.start()
            
            time.sleep(0.5)
            
            start_time = time.perf_counter()
            while self.flight_process.is_alive():
                time.sleep(0.1)
                if self.stop_event.is_set():
                    break
                if time.perf_counter() - start_time >= duration:
                    self.stop_event.set()
                    break
            
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
            QTimer.singleShot(0, self.experiment_finished)
    
    def start_live_monitor(self):
        """Start live monitoring with fresh data."""
        # Clear previous data for a fresh start
        self.clear_monitor_data()
        # Reset monitor buffer so we attach to the new shared memory
        if hasattr(self, '_monitor_buffer'):
            delattr(self, '_monitor_buffer')
        
        # Reset or create timer
        if self.monitor_timer is not None:
            self.monitor_timer.stop()
            self.monitor_timer = None
        
        self.monitor_timer = QTimer()
        self.monitor_timer.timeout.connect(self.update_live_monitor)
        self.monitor_timer.start(25)  # 40 Hz update
    
    def update_live_monitor(self):
        """Update live monitor plot with oscilloscope-style continuous timeline."""
        if not self.experiment_running or self.shared_buffer is None:
            # Stop timer if experiment is no longer running
            if self.monitor_timer is not None:
                self.monitor_timer.stop()
            return
        
        try:
            import time
            # Use experiment start time (never changes) for continuous timeline
            if self.experiment_start_time is None:
                self.experiment_start_time = time.perf_counter()
            
            # Current elapsed time since experiment started
            current_time = time.perf_counter() - self.experiment_start_time
            
            # Attach to shared memory if not already
            if not hasattr(self, '_monitor_buffer'):
                self._monitor_buffer = MotorStateBuffer(create=False)
            
            pwm_values = self._monitor_buffer.get_pwm()
            
            # Get value based on monitor type
            if self.monitor_type.currentText() == "Individual Motor":
                motor_id = self.monitor_motor_select.currentIndex()
                pwm_value = pwm_values[motor_id]
            else:  # Group Average
                group_index = self.monitor_group_select.currentIndex()
                if 0 <= group_index < len(self.groups):
                    group = self.groups[group_index]
                    if len(group.motors) > 0:
                        group_pwms = [pwm_values[m] for m in group.motors]
                        pwm_value = np.mean(group_pwms)
                    else:
                        pwm_value = PWM_MIN
                else:
                    pwm_value = PWM_MIN
            
            self.monitor_data_time.append(current_time)
            self.monitor_data_pwm.append(pwm_value)
            
            # Update plot with sliding 5-second window
            time_data = list(self.monitor_data_time)
            pwm_data = list(self.monitor_data_pwm)
            self.plot_curve.setData(time_data, pwm_data)
            
            # Auto-scale X-axis to show last 5 seconds (sliding window)
            if len(time_data) > 0:
                max_time = time_data[-1]
                min_time = max(0, max_time - 5.0)  # Show 5-second window
                self.plot_widget.setXRange(min_time, max_time + 0.5, padding=0)
            
        except Exception as e:
            print(f"[Monitor] Error: {e}")
    
    def stop_experiment(self):
        """Stop the running experiment immediately."""
        if self.experiment_running and self.stop_event:
            print("[GUI] Stop button pressed - stopping experiment...")
            self.stop_event.set()
            
            # Stop live monitoring timer completely
            if self.monitor_timer is not None:
                self.monitor_timer.stop()
                self.monitor_timer = None  # Reset timer object
            if hasattr(self, '_monitor_buffer'):
                delattr(self, '_monitor_buffer')
            
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
    
    def experiment_finished(self):
        """Called when experiment finishes."""
        self.experiment_running = False
        
        # Stop and clear live monitoring
        if self.monitor_timer is not None:
            self.monitor_timer.stop()
        
        # Reset experiment timeline for next experiment
        self.experiment_start_time = None
        self.clear_monitor_data()
        if hasattr(self, '_monitor_buffer'):
            delattr(self, '_monitor_buffer')
        
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
        
        # Stop live monitoring
        if self.monitor_timer:
            self.monitor_timer.stop()
        
        # Re-enable configuration
        self.groups_list.setEnabled(True)
        self.signal_type.setEnabled(True)
        for btn in self.motor_buttons:
            btn.setEnabled(True)
        
        QMessageBox.information(self, "Experiment Complete", 
                              "Experiment finished! Check the logs folder for data.")


def main_gui():
    """Main entry point for GUI."""
    multiprocessing.set_start_method('fork', force=True)
    
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    font = QFont("Arial", 10)
    app.setFont(font)
    
    window = WindWallGUI()
    window.show()
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main_gui()
