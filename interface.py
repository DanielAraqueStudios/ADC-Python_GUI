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
        self.timer = None

        # Add connection status at class level
        self.connection_status = None

        # Data buffers
        self.lux_data = []
        self.dist_data = []
        self.time_data = []  # Timestamps for the X-axis

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
        self.port_combo.clear()
        ports = serial.tools.list_ports.comports()
        for port in ports:
            self.port_combo.addItem(port.device)

    def initialize_graph_labels(self):
        """Set initial labels and titles for the graphs."""
        self.ax_lux.set_title("Light Intensity (%)")
        self.ax_lux.set_xlabel("Time")
        self.ax_lux.set_ylabel("Light (%)")
        self.ax_lux.legend(["Light (%)"], loc="upper right")

        self.ax_dist.set_title("Distance (cm)")
        self.ax_dist.set_xlabel("Time")
        self.ax_dist.set_ylabel("Distance (cm)")
        self.ax_dist.legend(["Distance (cm)"], loc="upper right")

        self.canvas.draw()

    def connect_serial(self):
        """Connect to the selected serial port."""
        try:
            selected_port = self.port_combo.currentText()
            if not selected_port:
                QMessageBox.warning(self, "Warning", "No serial port selected.")
                return
                
            self.serial_conn = serial.Serial(selected_port, self.baud_rate, timeout=1)
            self.connection_status.setText("Status: Connected")
            self.connection_status.setStyleSheet("color: green; font-weight: bold;")
            
            self.running = True
            self.serial_thread = threading.Thread(target=self.read_serial_data)
            self.serial_thread.daemon = True
            self.serial_thread.start()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Unable to connect to serial port: {str(e)}")
            self.connection_status.setText("Status: Disconnected")
            self.connection_status.setStyleSheet("color: red; font-weight: bold;")

    def read_serial_data(self):
        """Read data from the serial port in a separate thread."""
        try:
            while self.running:
                if not self.serial_conn or not self.serial_conn.is_open:
                    break
                
                try:
                    line = self.serial_conn.readline().decode().strip()
                    if line.startswith("TEMP:"):
                        value = float(line.split(":")[1])
                        self.add_data_point(value, "TEMP")
                    elif line.startswith("PESO:"):
                        value = float(line.split(":")[1])
                        self.add_data_point(value, "PESO")
                except Exception as e:
                    print(f"Error parsing data: {e}")
                    time.sleep(0.1)  # Avoid CPU hogging
                    
        except Exception as e:
            print(f"Error in serial thread: {e}")
        finally:
            print("Serial thread terminated")

    def add_data_point(self, value, data_type):
        """Add a data point to the appropriate buffer."""
        now = datetime.now()
        if data_type == "TEMP":
            self.lux_data.append(value)
        elif data_type == "PESO":
            self.dist_data.append(value)
        self.time_data.append(now)

        # Keep only the last 60 seconds or 10 minutes of data
        max_duration = timedelta(minutes=10) if self.time_unit_combo.currentText() == "min" else timedelta(seconds=60)
        while self.time_data and now - self.time_data[0] > max_duration:
            self.time_data.pop(0)
            if data_type == "TEMP":
                self.lux_data.pop(0)
            elif data_type == "PESO":
                self.dist_data.pop(0)

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
        """Start data acquisition."""
        try:
            if not self.use_simulated_data:
                self.connect_serial()
                
                # Send initial configuration to the microcontroller
                self.send_all_settings()
                
                # Start acquisition on STM32
                self.serial_conn.write(b"a\r\n")
                print("Sent start command")
            
            # Create and start the timer
            if self.timer is None:
                self.timer = QTimer()
                self.timer.timeout.connect(self.update_graphs)
            
            if not self.timer.isActive():
                self.timer.start(100)
                
            if self.use_simulated_data:
                self.connection_status.setText("Status: Simulated")
                self.connection_status.setStyleSheet("color: orange; font-weight: bold;")
        except Exception as e:
            print(f"Error starting acquisition: {e}")

    def stop_acquisition(self):
        """Stop data acquisition and close the serial connection safely."""
        try:
            # Send stop command to STM32 if connected
            if self.serial_conn and self.serial_conn.is_open:
                try:
                    self.serial_conn.write(b"b\r\n")
                    print("Sent stop command")
                except:
                    pass
            
            # First stop the timer to prevent concurrent access
            if self.timer and self.timer.isActive():
                self.timer.stop()
            
            # Signal the thread to stop and wait a bit
            self.running = False
            if self.serial_thread and self.serial_thread.is_alive():
                self.serial_thread.join(0.5)  # Wait for thread to finish
            
            # Close serial connection
            if self.serial_conn and self.serial_conn.is_open:
                try:
                    self.serial_conn.close()
                except:
                    pass
                    
            # Update UI
            self.connection_status.setText("Status: Disconnected")
            self.connection_status.setStyleSheet("color: red; font-weight: bold;")
        except Exception as e:
            print(f"Error stopping acquisition: {e}")

    def send_all_settings(self):
        """Send all current settings to the microcontroller."""
        try:
            if self.serial_conn and self.serial_conn.is_open:
                # Send time unit
                unit_map = {"ms": "m", "s": "s", "min": "M"}
                unit = unit_map[self.time_unit_combo.currentText()]
                self.serial_conn.write(f"TU:{unit}\r\n".encode())
                
                # Send sampling times
                self.serial_conn.write(f"T1:{self.t1_spinbox.value()}\r\n".encode())
                self.serial_conn.write(f"T2:{self.t2_spinbox.value()}\r\n".encode())
                
                # Send filter settings
                self.serial_conn.write(f"FT:{self.ft_combo.currentIndex()}\r\n".encode())
                self.serial_conn.write(f"FP:{self.fp_combo.currentIndex()}\r\n".encode())
                
                # Send filter sample counts
                self.serial_conn.write(f"ST:{self.st_spinbox.value()}\r\n".encode())
                self.serial_conn.write(f"SP:{self.sp_spinbox.value()}\r\n".encode())
                
                print("Sent all settings to microcontroller")
        except Exception as e:
            print(f"Error sending settings: {e}")

    def update_graphs(self):
        if self.is_paused:
            return

        if self.use_simulated_data:
            self.generate_simulated_data()

        self.ax_lux.clear()
        self.ax_dist.clear()

        # Smooth light data
        if len(self.time_data) > 3:
            time_numeric = [t.timestamp() for t in self.time_data]
            time_smooth = make_interp_spline(time_numeric, self.lux_data)(time_numeric)
            self.ax_lux.plot(self.time_data, time_smooth, label="Light (%)", color="blue", linestyle="-")
            self.ax_lux.scatter(self.time_data, self.lux_data, color="blue", s=10, label="Acquisition Points")
        else:
            self.ax_lux.plot(self.time_data, self.lux_data, label="Light (%)", color="blue", marker="o", linestyle="-")

        self.ax_lux.set_title("Light Intensity (%)")
        self.ax_lux.set_xlabel("Time")
        self.ax_lux.set_ylabel("Light (%)")
        self.ax_lux.legend()
        self.ax_lux.grid(True)

        # Smooth distance data
        if len(self.time_data) > 3:
            time_numeric = [t.timestamp() for t in self.time_data]
            dist_smooth = make_interp_spline(time_numeric, self.dist_data)(time_numeric)
            self.ax_dist.plot(self.time_data, dist_smooth, label="Distance (cm)", color="green", linestyle="-")
            self.ax_dist.scatter(self.time_data, self.dist_data, color="green", s=10, label="Acquisition Points")
        else:
            self.ax_dist.plot(self.time_data, self.dist_data, label="Distance (cm)", color="green", marker="o", linestyle="-")

        self.ax_dist.set_title("Distance (cm)")
        self.ax_dist.set_xlabel("Time")
        self.ax_dist.set_ylabel("Distance (cm)")
        self.ax_dist.legend()
        self.ax_dist.grid(True)

        self.canvas.draw()

    def generate_simulated_data(self):
        now = datetime.now()
        self.lux_data.append(random.uniform(0, 100))  # Simulated light percentage
        self.dist_data.append(random.uniform(10, 150))  # Simulated distance in cm
        self.time_data.append(now)

        # Keep only the last 60 seconds or 10 minutes of data
        max_duration = timedelta(minutes=10) if self.time_unit_combo.currentText() == "min" else timedelta(seconds=60)
        while self.time_data and now - self.time_data[0] > max_duration:
            self.time_data.pop(0)
            self.lux_data.pop(0)
            self.dist_data.pop(0)

    def closeEvent(self, event):
        """Handle the window close event safely."""
        try:
            self.stop_acquisition()
        except:
            pass
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = RealTimeGraph()
    window.show()
    sys.exit(app.exec_())
