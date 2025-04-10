import sys
import random
import serial
import time
import threading
from datetime import datetime, timedelta
from scipy.interpolate import make_interp_spline
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QWidget, QLabel, QPushButton, QComboBox, QSpinBox, QGridLayout, QMessageBox, QHBoxLayout
)
from PyQt5.QtCore import QTimer, Qt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import serial.tools.list_ports
import qdarkstyle

class RealTimeGraph(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Real-Time Sensor Monitoring")
        self.setGeometry(100, 100, 1200, 800)

        # Serial connection
        self.serial_port = None
        self.baud_rate = 9600
        self.serial_conn = None
        self.serial_thread = None
        self.running = False  # Thread control flag
        self.use_simulated_data = True  # Flag to toggle between simulated and real data
        self.is_paused = False  # Flag to pause/resume graphs
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_graphs)

        # Add connection status at class level
        self.connection_status = None

        # Data buffers
        self.lux_data = []
        self.dist_data = []
        self.time_data = []  # Timestamps for the X-axis

        # Data synchronization lock
        self.data_lock = threading.Lock()

        # Main layout
        self.main_widget = QWidget(self)
        self.setCentralWidget(self.main_widget)
        self.layout = QVBoxLayout(self.main_widget)

        # Graphs
        self.figure = Figure()
        self.canvas = FigureCanvas(self.figure)
        self.ax_lux = self.figure.add_subplot(211)
        self.ax_dist = self.figure.add_subplot(212)
        self.figure.subplots_adjust(hspace=0.5)  # Add space between graphs
        self.ax_lux.grid(True)  # Add grid to the light graph
        self.ax_dist.grid(True)  # Add grid to the distance graph
        self.layout.addWidget(self.canvas)

        # Initialize graph labels
        self.initialize_graph_labels()

        # Controls layout
        self.controls_layout = QGridLayout()
        self.layout.addLayout(self.controls_layout)

        # Section: Sensor Configuration
        self.add_section_title("Sensor Configuration")
        
        # Connection status
        self.connection_status = QLabel("Status: Disconnected")
        self.connection_status.setProperty("role", "status")
        self.connection_status.setProperty("status", "disconnected")
        self.connection_status.setStyleSheet("color: red; font-weight: bold;")
        self.controls_layout.addWidget(self.connection_status, 0, 0, 1, 1)

        # Toggle data source button
        self.toggle_data_button = QPushButton("Mode: Simulated")
        self.toggle_data_button.clicked.connect(self.toggle_data_source)
        self.controls_layout.addWidget(self.toggle_data_button, 0, 5)
        
        self.time_unit_label = QLabel("Time Unit:")
        self.time_unit_combo = QComboBox()
        self.time_unit_combo.addItems(["ms", "s", "min"])
        self.time_unit_combo.currentIndexChanged.connect(self.update_time_unit)
        self.controls_layout.addWidget(self.time_unit_label, 0, 1)
        self.controls_layout.addWidget(self.time_unit_combo, 0, 2)

        # Serial port selection
        self.port_label = QLabel("Select Port:")
        self.port_combo = QComboBox()
        self.refresh_ports()
        self.controls_layout.addWidget(self.port_label, 0, 3)
        self.controls_layout.addWidget(self.port_combo, 0, 4)

        # Temperature sensor controls
        self.add_section_title("Temperature Sensor")
        self.t1_label = QLabel("Sampling Time (s):")
        self.t1_spinbox = QSpinBox()
        self.t1_spinbox.setRange(1, 10000)
        self.t1_spinbox.setValue(1)
        self.t1_spinbox.valueChanged.connect(self.update_t1)
        self.controls_layout.addWidget(self.t1_label, 1, 0)
        self.controls_layout.addWidget(self.t1_spinbox, 1, 1)

        self.temp_real_time_label = QLabel("Real Time: --")
        self.controls_layout.addWidget(self.temp_real_time_label, 1, 2)

        self.ft_label = QLabel("Average Filter:")
        self.ft_combo = QComboBox()
        self.ft_combo.addItems(["Off", "On"])
        self.ft_combo.currentIndexChanged.connect(self.update_ft)
        self.controls_layout.addWidget(self.ft_label, 2, 0)
        self.controls_layout.addWidget(self.ft_combo, 2, 1)

        self.st_label = QLabel("Samples for Filtering:")
        self.st_spinbox = QSpinBox()
        self.st_spinbox.setRange(1, 50)
        self.st_spinbox.setValue(10)
        self.st_spinbox.valueChanged.connect(self.update_st)
        self.controls_layout.addWidget(self.st_label, 2, 2)

        # Light sensor controls
        self.add_section_title("Light Sensor")
        self.t2_label = QLabel("Sampling Time (s):")
        self.t2_spinbox = QSpinBox()
        self.t2_spinbox.setRange(1, 10000)
        self.t2_spinbox.setValue(1)
        self.t2_spinbox.valueChanged.connect(self.update_t2)
        self.controls_layout.addWidget(self.t2_label, 3, 0)
        self.controls_layout.addWidget(self.t2_spinbox, 3, 1)

        self.light_real_time_label = QLabel("Real Time: --")
        self.controls_layout.addWidget(self.light_real_time_label, 3, 2)

        self.fp_label = QLabel("Average Filter:")
        self.fp_combo = QComboBox()
        self.fp_combo.addItems(["Off", "On"])
        self.fp_combo.currentIndexChanged.connect(self.update_fp)
        self.controls_layout.addWidget(self.fp_label, 4, 0)
        self.controls_layout.addWidget(self.fp_combo, 4, 1)

        self.sp_label = QLabel("Samples for Filtering:")
        self.sp_spinbox = QSpinBox()
        self.sp_spinbox.setRange(1, 50)
        self.sp_spinbox.setValue(10)
        self.sp_spinbox.valueChanged.connect(self.update_sp)
        self.controls_layout.addWidget(self.sp_label, 4, 2)

        # Control Buttons
        self.start_button = QPushButton("Start")
        self.start_button.clicked.connect(self.start_acquisition)
        self.controls_layout.addWidget(self.start_button, 5, 0)

        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop_acquisition)
        self.controls_layout.addWidget(self.stop_button, 5, 1)

        self.pause_button = QPushButton("Pause/Resume Graphs")
        self.pause_button.clicked.connect(self.toggle_pause)
        self.controls_layout.addWidget(self.pause_button, 5, 2)

        # Apply dark theme
        self.apply_dark_theme()

    def apply_dark_theme(self):
        """Apply QDarkStyle theme."""
        self.setStyleSheet(qdarkstyle.load_stylesheet_pyqt5())

    def add_section_title(self, title):
        """Add a styled section title."""
        title_label = QLabel(title)
        title_label.setProperty("role", "section-title")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px; margin-top: 10px;")
        self.controls_layout.addWidget(title_label, self.controls_layout.rowCount(), 0, 1, 3)

    def refresh_ports(self):
        """Refresh available serial ports."""
        self.port_combo.clear()
        try:
            ports = serial.tools.list_ports.comports()
            for port in ports:
                self.port_combo.addItem(port.device)
            
            # Add refresh button
            if not hasattr(self, 'refresh_button'):
                self.refresh_button = QPushButton("Refresh")
                self.refresh_button.clicked.connect(self.refresh_ports)
                self.controls_layout.addWidget(self.refresh_button, 0, 6)
        except Exception as e:
            print(f"Error refreshing ports: {e}")

    def initialize_graph_labels(self):
        """Set initial labels and titles for the graphs."""
        self.ax_lux.set_title("Fotorresistencia - Intensidad Lumínica (%)")
        self.ax_lux.set_xlabel("Tiempo")
        self.ax_lux.set_ylabel("Intensidad Lumínica (%)")
        self.ax_lux.legend(["Intensidad Lumínica (%)"], loc="upper right")

        self.ax_dist.set_title("Sharp - Distancia (cm)")
        self.ax_dist.set_xlabel("Tiempo")
        self.ax_dist.set_ylabel("Distancia (cm)")
        self.ax_dist.legend(["Distancia (cm)"], loc="upper right")

        self.canvas.draw()

    def connect_serial(self):
        """Connect to the selected serial port with improved error handling."""
        try:
            selected_port = self.port_combo.currentText()
            if not selected_port:
                QMessageBox.warning(self, "Warning", "No serial port selected.")
                return
            
            # Close any existing connection first
            self.disconnect_serial()
                
            # Try to open with different configurations
            try:
                self.serial_conn = serial.Serial(
                    port=selected_port,
                    baudrate=self.baud_rate,
                    timeout=1,
                    write_timeout=1
                )
            except PermissionError:
                # Try to release the port in case it's held by another instance
                import subprocess
                import platform
                if platform.system() == "Windows":
                    try:
                        # Mode COM ports to force release
                        subprocess.call(["mode", selected_port])
                    except:
                        pass
                    
                # Try again after a short delay
                time.sleep(1)
                self.serial_conn = serial.Serial(
                    port=selected_port,
                    baudrate=self.baud_rate,
                    timeout=1,
                    write_timeout=1,
                    exclusive=False  # Try non-exclusive access on Windows
                )
            
            # Set up connection state
            self.connection_status.setText("Status: Connected")
            self.connection_status.setStyleSheet("color: green; font-weight: bold;")
            
            self.running = True
            self.serial_thread = threading.Thread(target=self.read_serial_data)
            self.serial_thread.daemon = True
            self.serial_thread.start()
            
        except serial.SerialException as e:
            QMessageBox.critical(self, "Error", f"Unable to connect to serial port: {str(e)}\n\nTry closing other applications using this port, or restarting your computer.")
            self.connection_status.setText("Status: Disconnected")
            self.connection_status.setStyleSheet("color: red; font-weight: bold;")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Unexpected error: {str(e)}")
            self.connection_status.setText("Status: Disconnected")
            self.connection_status.setStyleSheet("color: red; font-weight: bold;")

    def disconnect_serial(self):
        """Safely disconnect from serial port."""
        # First set the flag to signal the thread to stop
        self.running = False
        
        # Give the read thread time to exit with better exception handling
        try:
            if self.serial_thread and self.serial_thread.is_alive():
                self.serial_thread.join(0.5)  # Wait up to 0.5 seconds for thread to finish
        except Exception as e:
            print(f"Error waiting for thread to exit: {e}")
        
        # Now close the serial connection
        if hasattr(self, 'serial_conn') and self.serial_conn:
            try:
                if self.serial_conn.is_open:
                    self.serial_conn.close()
            except Exception as e:
                print(f"Error closing serial connection: {e}")
            self.serial_conn = None

    def read_serial_data(self):
        """Read data from the serial port in a separate thread with improved error handling."""
        print("Serial thread started")
        
        # Initialize data buffers with default values
        with self.data_lock:
            if not self.time_data:
                now = datetime.now()
                self.time_data = [now]
                self.lux_data = [0.0]
                self.dist_data = [0.0]
        
        while self.running:
            try:
                # Check if connection is still valid
                if not self.serial_conn or not self.serial_conn.is_open:
                    print("Serial connection lost or closed")
                    break
                
                # Non-blocking read with timeout
                if not self.serial_conn.in_waiting:
                    time.sleep(0.01)  # Small delay to avoid CPU hogging
                    continue
                
                try:
                    # Read a line with fixed buffer size to avoid overflow
                    line = self.serial_conn.readline(256).decode('latin-1', errors='replace').strip()
                    
                    # Skip empty lines
                    if not line:
                        continue
                        
                    # Debug incoming data to console
                    print(f"Received raw data: '{line}'")
                    
                    # Handle distance data (previously parsed as TEMP)
                    if line.startswith("TEMP:"):
                        try:
                            parts = line.split(":")
                            if len(parts) >= 2:
                                value_str = parts[1].strip()
                                value = float(value_str)
                                print(f"Parsed Sharp distance value: {value}")
                                
                                # Thread-safe data update using lock
                                with self.data_lock:
                                    now = datetime.now()
                                    self.dist_data.append(value)  # Now correctly goes to distance data
                                    self.time_data.append(now)
                                    print(f"Added Sharp distance data point: {value} at {now}")
                        except Exception as e:
                            print(f"Error parsing Sharp distance data: {e}, from line: '{line}'")
                    
                    # Handle light intensity data (previously parsed as PESO)
                    elif line.startswith("intensidad lumínica:"):
                        try:
                            parts = line.split(":")
                            if len(parts) >= 2:
                                value_str = parts[1].strip()
                                value = float(value_str)
                                print(f"Parsed light intensity value: {value}")
                                
                                # Thread-safe data update using lock
                                with self.data_lock:
                                    now = datetime.now()
                                    self.lux_data.append(value)  # Now correctly goes to light data
                                    
                                    # Only add a new timestamp if this is a completely new reading
                                    if not self.time_data or abs((now - self.time_data[-1]).total_seconds()) > 0.1:
                                        self.time_data.append(now)
                                    
                                    print(f"Added light intensity data point: {value} at {now}")
                        except Exception as e:
                            print(f"Error parsing light intensity data: {e}, from line: '{line}'")
                    
                    # Handle status and debug messages
                    elif line.startswith(("OK:", "INFO:", "ERROR:", "DEBUG:")):
                        print(f"STM32 message: {line}")
                        
                except Exception as e:
                    print(f"Error reading line: {e}")
                    time.sleep(0.1)  # Avoid tight loop on error
            
            except Exception as e:
                print(f"Serial thread exception: {e}")
                time.sleep(0.2)  # Brief delay on errors
                
        print("Serial thread exiting normally")

    def add_data_point(self, value, data_type):
        """Add a data point to the appropriate buffer (thread-safe)."""
        try:
            now = datetime.now()
            if data_type == "TEMP":
                self.lux_data.append(value)
                self.time_data.append(now)
            elif data_type == "PESO":
                self.dist_data.append(value)
                # Only add time point once per unique timestamp to avoid duplicates
                if not self.time_data or self.time_data[-1] != now:
                    self.time_data.append(now)

            # Keep only the last 60 seconds or 10 minutes of data
            max_duration = timedelta(minutes=10) if self.time_unit_combo.currentText() == "min" else timedelta(seconds=60)
            while self.time_data and now - self.time_data[0] > max_duration:
                self.time_data.pop(0)
                
                # Only remove data if it exists
                if len(self.lux_data) > 0 and data_type == "TEMP":
                    self.lux_data.pop(0)
                if len(self.dist_data) > 0 and data_type == "PESO":
                    self.dist_data.pop(0)
        except Exception as e:
            print(f"Error adding data point: {e}")

    def toggle_data_source(self):
        """Toggle between simulated and real data sources."""
        self.use_simulated_data = not self.use_simulated_data
        if self.use_simulated_data:
            self.toggle_data_button.setText("Mode: Simulated")
            QMessageBox.information(self, "Data Source", "Switched to simulated data source.")
        else:
            self.toggle_data_button.setText("Mode: Real")
            QMessageBox.information(self, "Data Source", "Switched to real data source.\nMake sure to select the correct port.")

    def toggle_pause(self):
        self.is_paused = not self.is_paused

    def update_time_unit(self):
        """Update the time unit for sampling."""
        unit_map = {"ms": "m", "s": "s", "min": "M"}  # Map interface options to STM32 expected values
        unit = unit_map[self.time_unit_combo.currentText()]
        
        # Update UI to show actual value sent
        print(f"Setting time unit to: {unit}")
        
        # Send to serial if connected
        if self.serial_conn and self.serial_conn.is_open:
            try:
                command = f"TU:{unit}\r\n"
                self.serial_conn.write(command.encode())
                print(f"Sent command: {command}")
            except Exception as e:
                print(f"Error sending time unit: {e}")

    def update_t1(self):
        """Update temperature/light sampling time."""
        value = self.t1_spinbox.value()
        
        # Update the real-time display
        unit_text = self.time_unit_combo.currentText()
        self.temp_real_time_label.setText(f"Real Time: {value} {unit_text}")
        
        # Send to serial if connected
        if self.serial_conn and self.serial_conn.is_open:
            try:
                command = f"T1:{value}\r\n"
                self.serial_conn.write(command.encode())
                print(f"Sent command: {command}")
            except Exception as e:
                print(f"Error sending T1: {e}")

    def update_t2(self):
        """Update weight/distance sampling time."""
        value = self.t2_spinbox.value()
        
        # Update the real-time display
        unit_text = self.time_unit_combo.currentText()
        self.light_real_time_label.setText(f"Real Time: {value} {unit_text}")
        
        # Send to serial if connected
        if self.serial_conn and self.serial_conn.is_open:
            try:
                command = f"T2:{value}\r\n"
                self.serial_conn.write(command.encode())
                print(f"Sent command: {command}")
            except Exception as e:
                print(f"Error sending T2: {e}")

    def update_ft(self):
        """Update temperature/light filter setting."""
        value = self.ft_combo.currentIndex()
        
        # Send to serial if connected
        if self.serial_conn and self.serial_conn.is_open:
            try:
                command = f"FT:{value}\r\n"
                self.serial_conn.write(command.encode())
                print(f"Sent command: {command}")
            except Exception as e:
                print(f"Error sending FT: {e}")

    def update_fp(self):
        """Update weight/distance filter setting."""
        value = self.fp_combo.currentIndex()
        
        # Send to serial if connected
        if self.serial_conn and self.serial_conn.is_open:
            try:
                command = f"FP:{value}\r\n"
                self.serial_conn.write(command.encode())
                print(f"Sent command: {command}")
            except Exception as e:
                print(f"Error sending FP: {e}")

    def update_st(self):
        """Update temperature/light filter sample count."""
        value = self.st_spinbox.value()
        
        # Send to serial if connected
        if self.serial_conn and self.serial_conn.is_open:
            try:
                command = f"ST:{value}\r\n"
                self.serial_conn.write(command.encode())
                print(f"Sent command: {command}")
            except Exception as e:
                print(f"Error sending ST: {e}")

    def update_sp(self):
        """Update weight/distance filter sample count."""
        value = self.sp_spinbox.value()
        
        # Send to serial if connected
        if self.serial_conn and self.serial_conn.is_open:
            try:
                command = f"SP:{value}\r\n"
                self.serial_conn.write(command.encode())
                print(f"Sent command: {command}")
            except Exception as e:
                print(f"Error sending SP: {e}")

    def start_acquisition(self):
        """Start data acquisition with improved error handling."""
        try:
            # Reset data buffers to ensure clean start
            with self.data_lock:
                self.time_data = []
                self.lux_data = []  # Fotorresistencia (intensidad lumínica)
                self.dist_data = []  # Sharp (distancia)
                
            # Update UI first
            self.connection_status.setText("Status: Starting...")
            self.connection_status.setStyleSheet("color: orange; font-weight: bold;")
            QApplication.processEvents()  # Force UI update
            
            # Start or ensure timer is running
            if not self.timer.isActive():
                self.timer.start(200)  # 5 Hz refresh rate - slower for stability
                
            # Handle real vs simulated data
            if not self.use_simulated_data:
                try:
                    # Make sure old connections are closed
                    self.disconnect_serial()
                    
                    # Connect to serial port
                    selected_port = self.port_combo.currentText()
                    if not selected_port:
                        QMessageBox.warning(self, "Warning", "No serial port selected.")
                        self.use_simulated_data = True
                        return
                    
                    # Open serial connection with robust error handling
                    try:
                        # First try with normal parameters
                        self.serial_conn = serial.Serial(
                            port=selected_port,
                            baudrate=self.baud_rate,
                            timeout=0.5,  # Short timeout for better responsiveness
                            write_timeout=0.5
                        )
                    except (serial.SerialException, PermissionError) as e:
                        print(f"First connection attempt failed: {e}")
                        
                        # Try to free the port if needed
                        try:
                            import os
                            if os.name == 'nt':  # Windows
                                os.system(f"mode {selected_port} baud=9600 parity=n data=8 stop=1")
                            time.sleep(1)
                            
                            # Second try with non-exclusive access (Windows)
                            self.serial_conn = serial.Serial(
                                port=selected_port,
                                baudrate=self.baud_rate,
                                timeout=0.5,
                                write_timeout=0.5,
                                exclusive=False
                            )
                        except Exception as e2:
                            print(f"Second connection attempt failed: {e2}")
                            raise e  # Raise the original error
                    
                    # Update UI for successful connection
                    self.connection_status.setText("Status: Connected")
                    self.connection_status.setStyleSheet("color: green; font-weight: bold;")
                    
                    # Start the read thread
                    self.running = True
                    self.serial_thread = threading.Thread(target=self.read_serial_data)
                    self.serial_thread.daemon = True  # Thread will exit when main program exits
                    self.serial_thread.start()
                    
                    # Give a moment for thread to start
                    time.sleep(0.1)
                    
                    # Send configuration commands to STM32
                    self.send_all_settings()
                    
                    # Send start command
                    time.sleep(0.2)  # Short delay before start command
                    self.serial_conn.write(b"a\r\n")
                    print("Start command sent")
                    
                    # Update UI status
                    self.connection_status.setText("Status: Acquiring Data")
                    self.connection_status.setStyleSheet("color: green; font-weight: bold;")
                    
                except Exception as e:
                    print(f"Error in serial connection: {e}")
                    QMessageBox.critical(self, "Connection Error",
                                        f"Could not connect to port {selected_port}.\n\n"
                                        f"Error: {str(e)}\n\n"
                                        "Switching to simulated data.")
                    self.use_simulated_data = True
                    self.connection_status.setText("Status: Using Simulation (Connection Failed)")
                    self.connection_status.setStyleSheet("color: orange; font-weight: bold;")
            
            # Set up for simulated data if needed
            if self.use_simulated_data:
                self.connection_status.setText("Status: Simulated Data")
                self.connection_status.setStyleSheet("color: orange; font-weight: bold;")
        
        except Exception as e:
            print(f"Critical error in start_acquisition: {e}")
            # Make sure UI stays responsive
            self.connection_status.setText("Status: Error")
            self.connection_status.setStyleSheet("color: red; font-weight: bold;")

    def send_all_settings(self):
        """Send all current settings to the microcontroller with improved error handling."""
        if not self.serial_conn or not self.serial_conn.is_open:
            print("Cannot send settings: Serial connection not open")
            return
            
        try:
            # Use a list of commands to send
            commands = []
            
            # Prepare all commands first
            unit_map = {"ms": "m", "s": "s", "min": "M"}
            unit = unit_map[self.time_unit_combo.currentText()]
            commands.append(f"TU:{unit}\r\n")
            
            commands.append(f"T1:{self.t1_spinbox.value()}\r\n")
            commands.append(f"T2:{self.t2_spinbox.value()}\r\n")
            
            commands.append(f"FT:{self.ft_combo.currentIndex()}\r\n")
            commands.append(f"FP:{self.fp_combo.currentIndex()}\r\n")
            
            commands.append(f"ST:{self.st_spinbox.value()}\r\n")
            commands.append(f"SP:{self.sp_spinbox.value()}\r\n")
            
            # Now send each command with delay between them
            for cmd in commands:
                self.serial_conn.write(cmd.encode())
                print(f"Sent: {cmd.strip()}")
                time.sleep(0.1)  # Short delay between commands
                
            print("All settings sent successfully")
        except Exception as e:
            print(f"Error sending settings: {e}")

    def stop_acquisition(self):
        """Stop data acquisition and close the serial connection safely."""
        try:
            # Update UI first
            self.connection_status.setText("Status: Stopping...")
            self.connection_status.setStyleSheet("color: orange; font-weight: bold;")
            QApplication.processEvents()  # Force UI update
            
            # Send stop command if connected to real hardware
            if self.serial_conn and self.serial_conn.is_open and not self.use_simulated_data:
                try:
                    self.serial_conn.write(b"b\r\n")
                    print("Stop command sent")
                    # Small delay to allow STM32 to process the command
                    time.sleep(0.2)
                except Exception as e:
                    print(f"Error sending stop command: {e}")
            
            # Stop the timer
            if self.timer.isActive():
                self.timer.stop()
            
            # Close serial connection
            self.disconnect_serial()
            
            # Update UI
            self.connection_status.setText("Status: Disconnected")
            self.connection_status.setStyleSheet("color: red; font-weight: bold;")
            
        except Exception as e:
            print(f"Error in stop_acquisition: {e}")
            self.connection_status.setText("Status: Error")
            self.connection_status.setStyleSheet("color: red; font-weight: bold;")

    def update_graphs(self):
        """Update graphs with thread-safety and debug output."""
        try:
            if self.is_paused:
                return

            # For simulated data or initial state
            if self.use_simulated_data:
                self.generate_simulated_data()

            # Make a thread-safe copy of the data
            with self.data_lock:
                time_data = self.time_data.copy() if self.time_data else []
                lux_data = self.lux_data.copy() if self.lux_data else []
                dist_data = self.dist_data.copy() if self.dist_data else []
                
                # Ensure we have equal length arrays by duplicating the last value if needed
                if len(lux_data) < len(time_data):
                    print(f"Padding lux data from {len(lux_data)} to {len(time_data)} points")
                    last_value = lux_data[-1] if lux_data else 0
                    lux_data.extend([last_value] * (len(time_data) - len(lux_data)))
                    
                if len(dist_data) < len(time_data):
                    print(f"Padding distance data from {len(dist_data)} to {len(time_data)} points")
                    last_value = dist_data[-1] if dist_data else 0
                    dist_data.extend([last_value] * (len(time_data) - len(dist_data)))
                
                # Trim extra data if needed
                time_data = time_data[:min(len(time_data), len(lux_data), len(dist_data))]
                lux_data = lux_data[:len(time_data)]
                dist_data = dist_data[:len(time_data)]
            
            # Print debug info about data
            print(f"Data status: Time points={len(time_data)}, Light points={len(lux_data)}, Distance points={len(dist_data)}")
            
            # Skip update if there's no data
            if not time_data or len(time_data) == 0:
                print("No data to plot yet, skipping graph update")
                return
                
            # Clear previous plots
            self.ax_lux.clear()
            self.ax_dist.clear()

            # Set grid for both plots
            self.ax_lux.grid(True)
            self.ax_dist.grid(True)
            
            # Plot the light data
            try:
                self.ax_lux.plot(time_data, lux_data, label="Light (%)", color="blue", marker="o", linestyle="-", markersize=4)
            except Exception as e:
                print(f"Error plotting light data: {e}")
                
            # Plot the distance data
            try:
                self.ax_dist.plot(time_data, dist_data, label="Distance (cm)", color="green", marker="o", linestyle="-", markersize=4)
            except Exception as e:
                print(f"Error plotting distance data: {e}")
            
            # Set titles and labels
            self.ax_lux.set_title("Fotorresistencia - Intensidad Lumínica (%)")
            self.ax_lux.set_xlabel("Tiempo")
            self.ax_lux.set_ylabel("Intensidad Lumínica (%)")
            self.ax_lux.legend()
            
            self.ax_dist.set_title("Sharp - Distancia (cm)")
            self.ax_dist.set_xlabel("Tiempo")
            self.ax_dist.set_ylabel("Distancia (cm)")
            self.ax_dist.legend()
            
            # Format time axis for better readability
            from matplotlib.dates import DateFormatter
            date_format = DateFormatter('%H:%M:%S')
            self.ax_lux.xaxis.set_major_formatter(date_format)
            self.ax_dist.xaxis.set_major_formatter(date_format)
            
            # Rotate date labels for better readability
            for label in self.ax_lux.get_xticklabels():
                label.set_rotation(45)
                label.set_ha('right')
            
            for label in self.ax_dist.get_xticklabels():
                label.set_rotation(45)
                label.set_ha('right')
                
            # Auto-adjust spacing to prevent overlapping
            self.figure.tight_layout()
            
            # Update the figure
            self.canvas.draw()
            
            print("Graph updated successfully")
                
        except Exception as e:
            print(f"Critical error in update_graphs: {e}")
            import traceback
            traceback.print_exc()

    def generate_simulated_data(self):
        """Generate simulated data with thread safety."""
        try:
            now = datetime.now()
            
            with self.data_lock:
                # Add both light and distance data with the same timestamp
                self.lux_data.append(random.uniform(0, 100))
                self.dist_data.append(random.uniform(10, 150))
                self.time_data.append(now)

                # Keep only the last 60 seconds or 10 minutes of data
                max_duration = timedelta(minutes=10) if self.time_unit_combo.currentText() == "min" else timedelta(seconds=60)
                while len(self.time_data) > 1 and now - self.time_data[0] > max_duration:
                    self.time_data.pop(0)
                    if self.lux_data:
                        self.lux_data.pop(0)
                    if self.dist_data:
                        self.dist_data.pop(0)
        except Exception as e:
            print(f"Error generating simulated data: {e}")

    def closeEvent(self, event):
        """Handle the window close event safely."""
        try:
            print("Application closing...")
            # Stop acquisition and disconnect
            if hasattr(self, 'timer') and self.timer and self.timer.isActive():
                self.timer.stop()
            
            # Signal thread to stop and close connection
            self.running = False
            if hasattr(self, 'serial_conn') and self.serial_conn and self.serial_conn.is_open:
                try:
                    self.serial_conn.write(b"b\r\n")  # Send stop command
                    time.sleep(0.2)  # Give time for command to be processed
                    self.serial_conn.close()
                except:
                    pass
        except:
            pass
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = RealTimeGraph()
    window.show()
    sys.exit(app.exec_())
