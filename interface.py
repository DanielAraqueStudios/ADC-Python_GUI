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
        self.setWindowTitle("Monitoreo de Sensores en Tiempo Real")
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
        
        # Flag to indicate time unit change (prevents recursion)
        self.updating_time_unit = False

        # Add connection status at class level
        self.connection_status = None

        # Data buffers - separamos más claramente los datos de cada sensor
        self.lux_data = []       # Datos de intensidad lumínica
        self.lux_times = []      # Timestamps específicos para intensidad lumínica
        self.dist_data = []      # Datos de distancia
        self.dist_times = []     # Timestamps específicos para distancia
        
        # Banderas para controlar si estamos recibiendo datos dentro del intervalo correcto
        self.last_t1_time = None  # Último tiempo de muestreo para sensor de distancia
        self.last_t2_time = None  # Último tiempo de muestreo para sensor de luz

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
        self.add_section_title("Configuración del Sistema")
        
        # Connection status
        self.connection_status = QLabel("Estado: Desconectado")
        self.connection_status.setProperty("role", "status")
        self.connection_status.setProperty("status", "disconnected")
        self.connection_status.setStyleSheet("color: red; font-weight: bold;")
        self.controls_layout.addWidget(self.connection_status, 0, 0, 1, 1)

        # Toggle data source button
        self.toggle_data_button = QPushButton("Modo: Simulado")
        self.toggle_data_button.clicked.connect(self.toggle_data_source)
        self.controls_layout.addWidget(self.toggle_data_button, 0, 5)
        
        self.time_unit_label = QLabel("Unidad de Tiempo:")
        self.time_unit_combo = QComboBox()
        self.time_unit_combo.addItems(["ms", "s", "min"])
        self.time_unit_combo.setCurrentIndex(1)  # Default to seconds
        self.time_unit_combo.currentIndexChanged.connect(self.update_time_unit)
        self.controls_layout.addWidget(self.time_unit_label, 0, 1)
        self.controls_layout.addWidget(self.time_unit_combo, 0, 2)

        # Serial port selection
        self.port_label = QLabel("Puerto Serial:")
        self.port_combo = QComboBox()
        self.refresh_ports()
        self.controls_layout.addWidget(self.port_label, 0, 3)
        self.controls_layout.addWidget(self.port_combo, 0, 4)

        # Sensor de Distancia Sharp
        self.add_section_title("Sensor de Distancia Sharp")
        self.t1_label = QLabel("Tiempo de Muestreo:")
        self.t1_spinbox = QSpinBox()
        self.t1_spinbox.setRange(1, 10000)
        self.t1_spinbox.setValue(1)
        self.t1_spinbox.valueChanged.connect(self.update_t1)
        self.controls_layout.addWidget(self.t1_label, 1, 0)
        self.controls_layout.addWidget(self.t1_spinbox, 1, 1)

        self.temp_real_time_label = QLabel("Tiempo Real: 1 s")
        self.controls_layout.addWidget(self.temp_real_time_label, 1, 2)

        self.ft_label = QLabel("Filtro Promedio:")
        self.ft_combo = QComboBox()
        self.ft_combo.addItems(["Desactivado", "Activado"])
        self.ft_combo.currentIndexChanged.connect(self.update_ft)
        self.controls_layout.addWidget(self.ft_label, 2, 0)
        self.controls_layout.addWidget(self.ft_combo, 2, 1)

        self.st_label = QLabel("Muestras para Filtro:")
        self.st_spinbox = QSpinBox()
        self.st_spinbox.setRange(1, 50)
        self.st_spinbox.setValue(10)
        self.st_spinbox.valueChanged.connect(self.update_st)
        self.controls_layout.addWidget(self.st_label, 2, 2)
        
        # Nuevo: Valor actual del sensor
        self.dist_value_label = QLabel("Valor Actual: -- cm")
        self.dist_value_label.setStyleSheet("font-weight: bold; color: green;")
        self.controls_layout.addWidget(self.dist_value_label, 1, 3, 1, 2)

        # Sensor de Luz / Fotorresistencia
        self.add_section_title("Sensor de Luz / Fotorresistencia")
        self.t2_label = QLabel("Tiempo de Muestreo:")
        self.t2_spinbox = QSpinBox()
        self.t2_spinbox.setRange(1, 10000)
        self.t2_spinbox.setValue(1)
        self.t2_spinbox.valueChanged.connect(self.update_t2)
        self.controls_layout.addWidget(self.t2_label, 3, 0)
        self.controls_layout.addWidget(self.t2_spinbox, 3, 1)

        self.light_real_time_label = QLabel("Tiempo Real: 1 s")
        self.controls_layout.addWidget(self.light_real_time_label, 3, 2)

        self.fl_label = QLabel("Filtro Promedio:")
        self.fl_combo = QComboBox()
        self.fl_combo.addItems(["Desactivado", "Activado"])
        self.fl_combo.currentIndexChanged.connect(self.update_fl)
        self.controls_layout.addWidget(self.fl_label, 4, 0)
        self.controls_layout.addWidget(self.fl_combo, 4, 1)

        self.sl_label = QLabel("Muestras para Filtro:")
        self.sl_spinbox = QSpinBox()
        self.sl_spinbox.setRange(1, 50)
        self.sl_spinbox.setValue(10)
        self.sl_spinbox.valueChanged.connect(self.update_sl)
        self.controls_layout.addWidget(self.sl_label, 4, 2)
        
        # Nuevo: Valor actual del sensor
        self.lux_value_label = QLabel("Valor Actual: -- %")
        self.lux_value_label.setStyleSheet("font-weight: bold; color: blue;")
        self.controls_layout.addWidget(self.lux_value_label, 3, 3, 1, 2)

        # Control Buttons
        self.start_button = QPushButton("Iniciar")
        self.start_button.clicked.connect(self.start_acquisition)
        self.controls_layout.addWidget(self.start_button, 5, 0)

        self.stop_button = QPushButton("Detener")
        self.stop_button.clicked.connect(self.stop_acquisition)
        self.controls_layout.addWidget(self.stop_button, 5, 1)

        self.pause_button = QPushButton("Pausar/Reanudar Gráficas")
        self.pause_button.clicked.connect(self.toggle_pause)
        self.controls_layout.addWidget(self.pause_button, 5, 2)
        
        # Nuevo: Botón para sincronizar configuración
        self.sync_button = QPushButton("Sincronizar Configuración")
        self.sync_button.clicked.connect(self.sync_all_settings)
        self.controls_layout.addWidget(self.sync_button, 5, 3)

        # Apply dark theme
        self.apply_dark_theme()
        
        # Inicializar etiquetas de tiempo según unidad seleccionada
        self.update_time_labels()

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
        """Refresh available serial ports and reset graph data."""
        self.port_combo.clear()
        try:
            ports = serial.tools.list_ports.comports()
            for port in ports:
                self.port_combo.addItem(port.device)
            
            # Add refresh button if it doesn't exist
            if not hasattr(self, 'refresh_button'):
                self.refresh_button = QPushButton("Refresh & Reset")
                self.refresh_button.clicked.connect(self.reset_and_refresh)
                self.controls_layout.addWidget(self.refresh_button, 0, 6)
        except Exception as e:
            print(f"Error refreshing ports: {e}")

    def reset_and_refresh(self):
        """Reset graph data and refresh ports."""
        # Clear all data arrays with thread safety
        with self.data_lock:
            # Actualizar para usar los nuevos arrays
            self.dist_times = []
            self.lux_times = []
            self.dist_data = []
            self.lux_data = []
            
        # Redraw empty graphs
        self.initialize_graph_labels()
            
        # Refresh ports
        self.port_combo.clear()
        try:
            ports = serial.tools.list_ports.comports()
            for port in ports:
                self.port_combo.addItem(port.device)
            print("Ports refreshed and graphs reset")
        except Exception as e:
            print(f"Error refreshing ports: {e}")

    def initialize_graph_labels(self):
        """Set initial labels and titles for the graphs."""
        # Clear existing plots
        self.ax_lux.clear()
        self.ax_dist.clear()
        
        # Ensure grid is visible
        self.ax_lux.grid(True)
        self.ax_dist.grid(True)
        
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
        """Read data from the serial port respecting sampling intervals."""
        print("Serial thread started")
        
        # Initialize data buffers with default values
        with self.data_lock:
            now = datetime.now()
            self.dist_times = []  # Inicializamos vacíos - solo agregamos puntos en intervalos correctos
            self.lux_times = []
            self.dist_data = []
            self.lux_data = []
            # Inicializamos los tiempos de último muestreo
            self.last_t1_time = now
            self.last_t2_time = now
        
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
                    
                    # Handle distance data (TEMP)
                    if line.startswith("TEMP:"):
                        try:
                            parts = line.split(":")
                            if len(parts) >= 2:
                                value_str = parts[1].strip()
                                value = float(value_str)
                                now = datetime.now()
                                
                                # Actualizamos siempre el valor actual en la UI
                                QApplication.instance().processEvents()
                                self.dist_value_label.setText(f"Valor Actual: {value:.2f} cm")
                                
                                # Verificamos si este punto debe registrarse según el intervalo de muestreo
                                if not self.last_t1_time or (now - self.last_t1_time).total_seconds() * 1000 >= self.t1_interval_ms:
                                    # Solo agregamos el punto si corresponde al intervalo
                                    with self.data_lock:
                                        self.dist_data.append(value)
                                        self.dist_times.append(now)
                                        self.last_t1_time = now
                                        print(f"Added Sharp distance data point at interval: {value:.2f} cm at {now}")
                                else:
                                    # Ignoramos esta lectura, está fuera del intervalo de muestreo
                                    print(f"Skipping Sharp reading - outside sampling interval: {value:.2f} cm")
                                    
                        except Exception as e:
                            print(f"Error parsing Sharp distance data: {e}, from line: '{line}'")
                    
                    # Handle light intensity data
                    elif line.startswith("intensidad lumínica:"):
                        try:
                            parts = line.split(":")
                            if len(parts) >= 2:
                                value_str = parts[1].strip()
                                value = float(value_str)
                                now = datetime.now()
                                
                                # Actualizamos siempre el valor actual en la UI
                                QApplication.instance().processEvents()
                                self.lux_value_label.setText(f"Valor Actual: {value:.2f} %")
                                
                                # Verificamos si este punto debe registrarse según el intervalo de muestreo
                                if not self.last_t2_time or (now - self.last_t2_time).total_seconds() * 1000 >= self.t2_interval_ms:
                                    # Solo agregamos el punto si corresponde al intervalo
                                    with self.data_lock:
                                        self.lux_data.append(value)
                                        self.lux_times.append(now)
                                        self.last_t2_time = now
                                        print(f"Added light intensity data point at interval: {value:.2f} % at {now}")
                                else:
                                    # Ignoramos esta lectura, está fuera del intervalo de muestreo
                                    print(f"Skipping light reading - outside sampling interval: {value:.2f} %")
                                
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
            self.toggle_data_button.setText("Modo: Simulado")
            QMessageBox.information(self, "Fuente de Datos", "Cambiado a fuente de datos simulada.")
        else:
            self.toggle_data_button.setText("Modo: Real")
            QMessageBox.information(self, "Fuente de Datos", "Cambiado a fuente de datos real.\nAsegúrese de seleccionar el puerto correcto.")

    def toggle_pause(self):
        self.is_paused = not self.is_paused

    def update_time_unit(self):
        """Update the time unit for sampling."""
        # Prevent recursive calls or processing while already updating
        if self.updating_time_unit:
            return
            
        self.updating_time_unit = True
        try:
            # Guardar valores actuales antes del cambio
            old_t1 = self.t1_spinbox.value()
            old_t2 = self.t2_spinbox.value()
            old_unit = self.time_unit_combo.currentText()
            new_unit = self.time_unit_combo.currentText()
            
            unit_map = {"ms": "m", "s": "s", "min": "M"}  # Map interface options to STM32 expected values
            unit = unit_map[new_unit]
            
            # Update UI to show actual value sent
            print(f"Setting time unit to: {unit}")
            
            # Clear existing data when changing time units to prevent scale issues
            with self.data_lock:
                self.dist_times = []
                self.lux_times = []
                self.dist_data = []
                self.lux_data = []
            
            # Send to serial if connected
            if self.serial_conn and self.serial_conn.is_open:
                try:
                    # Primero enviar el cambio de unidad
                    command = f"TU:{unit}\r\n"
                    self.serial_conn.write(command.encode())
                    print(f"Sent command: {command}")
                    time.sleep(0.1)  # Pequeña pausa para asegurar que se procese
                    
                    # Luego volver a enviar los tiempos de muestreo para asegurar consistencia
                    self.serial_conn.write(f"T1:{self.t1_spinbox.value()}\r\n".encode())
                    self.serial_conn.write(f"T2:{self.t2_spinbox.value()}\r\n".encode())
                    print(f"Resent sampling times with new unit: {new_unit}")
                except Exception as e:
                    print(f"Error sending time unit: {e}")
            
            # Actualizar etiquetas de tiempo
            self.update_time_labels()
            
            # Si el timer está activo, actualizar su intervalo
            if self.timer.isActive():
                update_rate = min(
                    self.calculate_real_sampling_time(self.t1_spinbox.value()),
                    self.calculate_real_sampling_time(self.t2_spinbox.value())
                )
                update_rate = min(max(update_rate, 100), 1000)  # Entre 100ms y 1000ms
                self.timer.setInterval(update_rate)
                print(f"Timer interval updated to {update_rate}ms after unit change")
            
            # Actualizar los intervalos de muestreo simulados si están activos
            if hasattr(self, 't1_interval'):
                self.t1_interval = self.calculate_real_sampling_time(self.t1_spinbox.value())
                print(f"T1 interval updated to {self.t1_interval}ms")
            
            if hasattr(self, 't2_interval'):
                self.t2_interval = self.calculate_real_sampling_time(self.t2_spinbox.value())
                print(f"T2 interval updated to {self.t2_interval}ms")
            
            # Reset simulation next sampling times with new intervals
            if hasattr(self, 'next_t1_sample_time'):
                self.t1_interval_ms = self.calculate_real_sampling_time(self.t1_spinbox.value())
                self.next_t1_sample_time = datetime.now()
                print(f"T1 interval reset to {self.t1_interval_ms}ms")
            
            if hasattr(self, 'next_t2_sample_time'):
                self.t2_interval_ms = self.calculate_real_sampling_time(self.t2_spinbox.value())
                self.next_t2_sample_time = datetime.now()
                print(f"T2 interval reset to {self.t2_interval_ms}ms")
            
        finally:
            # Always ensure we reset the flag
            self.updating_time_unit = False
    
    def update_time_labels(self):
        """Update time labels to reflect the current time unit."""
        unit_text = self.time_unit_combo.currentText()
        self.temp_real_time_label.setText(f"Tiempo Real: {self.t1_spinbox.value()} {unit_text}")
        self.light_real_time_label.setText(f"Tiempo Real: {self.t2_spinbox.value()} {unit_text}")

    def update_t1(self):
        """Update Sharp sensor sampling time."""
        value = self.t1_spinbox.value()
        
        # Update the real-time display
        unit_text = self.time_unit_combo.currentText()
        self.temp_real_time_label.setText(f"Tiempo Real: {value} {unit_text}")
        
        # Update simulation intervals if active
        if hasattr(self, 't1_interval'):
            self.t1_interval = self.calculate_real_sampling_time(value)
            print(f"T1 interval updated to {self.t1_interval}ms")
        
        # Send to serial if connected
        if self.serial_conn and self.serial_conn.is_open:
            try:
                command = f"T1:{value}\r\n"
                self.serial_conn.write(command.encode())
                print(f"Sent command: {command}")
                
                # Actualizar la tasa de refresco de la interfaz si es necesario
                if self.timer.isActive():
                    update_rate = min(
                        self.calculate_real_sampling_time(value),
                        self.calculate_real_sampling_time(self.t2_spinbox.value())
                    )
                    update_rate = min(max(update_rate, 100), 1000)  # Entre 100ms y 1000ms
                    self.timer.setInterval(update_rate)
                    print(f"Timer interval updated to {update_rate}ms after T1 change")
            except Exception as e:
                print(f"Error sending T1: {e}")
        
        # Update simulation next sampling time with new interval
        if hasattr(self, 'next_t1_sample_time'):
            self.t1_interval_ms = self.calculate_real_sampling_time(value)
            self.next_t1_sample_time = datetime.now() + timedelta(milliseconds=self.t1_interval_ms)
            print(f"T1 interval updated to {self.t1_interval_ms}ms, next sample at {self.next_t1_sample_time.strftime('%H:%M:%S.%f')}")

    def update_t2(self):
        """Update photoresistor sampling time."""
        value = self.t2_spinbox.value()
        
        # Update the real-time display
        unit_text = self.time_unit_combo.currentText()
        self.light_real_time_label.setText(f"Tiempo Real: {value} {unit_text}")
        
        # Update simulation intervals if active
        if hasattr(self, 't2_interval'):
            self.t2_interval = self.calculate_real_sampling_time(value)
            print(f"T2 interval updated to {self.t2_interval}ms")
        
        # Send to serial if connected
        if self.serial_conn and self.serial_conn.is_open:
            try:
                command = f"T2:{value}\r\n"
                self.serial_conn.write(command.encode())
                print(f"Sent command: {command}")
                
                # Actualizar la tasa de refresco de la interfaz si es necesario
                if self.timer.isActive():
                    update_rate = min(
                        self.calculate_real_sampling_time(self.t1_spinbox.value()),
                        self.calculate_real_sampling_time(value)
                    )
                    update_rate = min(max(update_rate, 100), 1000)  # Entre 100ms y 1000ms
                    self.timer.setInterval(update_rate)
                    print(f"Timer interval updated to {update_rate}ms after T2 change")
            except Exception as e:
                print(f"Error sending T2: {e}")
        
        # Update simulation next sampling time with new interval
        if hasattr(self, 'next_t2_sample_time'):
            self.t2_interval_ms = self.calculate_real_sampling_time(value)
            self.next_t2_sample_time = datetime.now() + timedelta(milliseconds=self.t2_interval_ms)
            print(f"T2 interval updated to {self.t2_interval_ms}ms, next sample at {self.next_t2_sample_time.strftime('%H:%M:%S.%f')}")

    def update_ft(self):
        """Update Sharp sensor filter setting."""
        value = self.ft_combo.currentIndex()
        
        # Send to serial if connected
        if self.serial_conn and self.serial_conn.is_open:
            try:
                command = f"FT:{value}\r\n"
                self.serial_conn.write(command.encode())
                print(f"Sent command: {command}")
            except Exception as e:
                print(f"Error sending FT: {e}")

    def update_fl(self):
        """Update light sensor filter setting."""
        value = self.fl_combo.currentIndex()
        
        # Send to serial if connected
        if self.serial_conn and self.serial_conn.is_open:
            try:
                command = f"FL:{value}\r\n"
                self.serial_conn.write(command.encode())
                print(f"Sent command: {command}")
            except Exception as e:
                print(f"Error sending FL: {e}")

    def update_st(self):
        """Update Sharp sensor filter sample count."""
        value = self.st_spinbox.value()
        
        # Send to serial if connected
        if self.serial_conn and self.serial_conn.is_open:
            try:
                command = f"ST:{value}\r\n"
                self.serial_conn.write(command.encode())
                print(f"Sent command: {command}")
            except Exception as e:
                print(f"Error sending ST: {e}")

    def update_sl(self):
        """Update light sensor filter sample count."""
        value = self.sl_spinbox.value()
        
        # Send to serial if connected
        if self.serial_conn and self.serial_conn.is_open:
            try:
                command = f"SL:{value}\r\n"
                self.serial_conn.write(command.encode())
                print(f"Sent command: {command}")
            except Exception as e:
                print(f"Error sending SL: {e}")
    
    def sync_all_settings(self):
        """Synchronize all settings with the STM32."""
        if not self.serial_conn or not self.serial_conn.is_open:
            QMessageBox.warning(self, "Advertencia", "No hay conexión serial activa.")
            return
            
        try:
            # Mostrar mensaje de sincronización
            self.connection_status.setText("Estado: Sincronizando...")
            self.connection_status.setStyleSheet("color: orange; font-weight: bold;")
            QApplication.processEvents()
            
            # Enviar todos los ajustes
            self.send_all_settings()
            
            # Reset sampling times after synchronizing
            now = datetime.now()
            self.last_t1_time = now
            self.last_t2_time = now
            
            # Mostrar mensaje de éxito
            self.connection_status.setText("Estado: Sincronizado")
            self.connection_status.setStyleSheet("color: green; font-weight: bold;")
            QMessageBox.information(self, "Sincronización", "Configuración sincronizada correctamente.")
        except Exception as e:
            print(f"Error sincronizando: {e}")
            self.connection_status.setText("Estado: Error")
            self.connection_status.setStyleSheet("color: red; font-weight: bold;")

    def send_all_settings(self):
        """Send all current settings to the microcontroller with improved error handling."""
        if not self.serial_conn or not self.serial_conn.is_open:
            print("Cannot send settings: Serial connection not open")
            return
            
        try:
            # Use a list of commands to send
            commands = []
            
            # Prepare all commands first - El orden es importante
            # Primero la unidad de tiempo, luego los demás parámetros
            unit_map = {"ms": "m", "s": "s", "min": "M"}
            unit = unit_map[self.time_unit_combo.currentText()]
            commands.append(f"TU:{unit}\r\n")
            
            commands.append(f"T1:{self.t1_spinbox.value()}\r\n")
            commands.append(f"T2:{self.t2_spinbox.value()}\r\n")
            
            commands.append(f"FT:{self.ft_combo.currentIndex()}\r\n")
            commands.append(f"FL:{self.fl_combo.currentIndex()}\r\n")
            
            commands.append(f"ST:{self.st_spinbox.value()}\r\n")
            commands.append(f"SL:{self.sl_spinbox.value()}\r\n")
            
            # Now send each command with delay between them
            for cmd in commands:
                self.serial_conn.write(cmd.encode())
                print(f"Sent: {cmd.strip()}")
                time.sleep(0.15)  # Aumentar delay entre comandos para asegurar procesamiento
                
            # Confirmar que la configuración fue recibida
            self.serial_conn.write(b"STATUS\r\n")
            print("Sent: STATUS - requesting confirmation of settings")
                
            print("All settings sent successfully")
            
            # Store the intervals locally for filtering
            self.t1_interval_ms = self.calculate_real_sampling_time(self.t1_spinbox.value())
            self.t2_interval_ms = self.calculate_real_sampling_time(self.t2_spinbox.value())
            
        except Exception as e:
            print(f"Error sending settings: {e}")

    def calculate_real_sampling_time(self, value):
        """Calcula el tiempo real de muestreo en milisegundos según la lógica del firmware STM32."""
        unit = self.time_unit_combo.currentText()
        # Replicamos exactamente la misma lógica del firmware STM32 (ver GraphCode.cpp)
        if unit == "ms":
            factor = 1
        elif unit == "s":
            factor = 1000
        elif unit == "min":
            factor = 60000
        else:
            factor = 1000  # Valor predeterminado es segundos
            
        arr_value = value * factor
        if arr_value < 1:
            arr_value = 1
            
        return arr_value

    def start_acquisition(self):
        """Start data acquisition with improved error handling."""
        try:
            # Reset data buffers to ensure clean start
            with self.data_lock:
                self.dist_times = []
                self.lux_times = []
                self.dist_data = []
                self.lux_data = []
                
            # Asegurar que tenemos un punto inicial para evitar grafos vacíos
            now = datetime.now()
            with self.data_lock:
                # Inicialización con al menos un punto de datos
                if len(self.dist_data) == 0:
                    self.dist_data.append(0.0)
                    self.dist_times.append(now)
                if len(self.lux_data) == 0:
                    self.lux_data.append(0.0)
                    self.lux_times.append(now)
                
            # Update UI first
            self.connection_status.setText("Estado: Iniciando...")
            self.connection_status.setStyleSheet("color: orange; font-weight: bold;")
            QApplication.processEvents()  # Force UI update
            
            # Calcular intervalos de muestreo
            self.t1_interval_ms = self.calculate_real_sampling_time(self.t1_spinbox.value())
            self.t2_interval_ms = self.calculate_real_sampling_time(self.t2_spinbox.value())
            
            # Inicializar tiempos de último muestreo
            now = datetime.now()
            self.last_t1_time = now
            self.last_t2_time = now
            self.next_t1_sample_time = now  # Para datos simulados
            self.next_t2_sample_time = now  # Para datos simulados
            
            print(f"Configured T1 sampling every {self.t1_interval_ms}ms")
            print(f"Configured T2 sampling every {self.t2_interval_ms}ms")
            
            # Start or ensure timer is running - timer is just for UI updates, not for sampling
            if not self.timer.isActive():
                # Fixed update rate for UI refreshes, sampling is controlled separately
                update_rate = 100  # Refresh UI every 100ms (10 Hz) regardless of sampling rate
                self.timer.start(update_rate)
                print(f"Interfaz configurada para actualizarse cada {update_rate}ms")
            
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
            
            # Asegurar actualización de gráficos inmediata
            self.update_graphs()
            
        except Exception as e:
            print(f"Critical error in start_acquisition: {e}")
            import traceback
            traceback.print_exc()
            # Make sure UI stays responsive
            self.connection_status.setText("Status: Error")
            self.connection_status.setStyleSheet("color: red; font-weight: bold;")

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
        # Don't update graphs during time unit change
        if self.updating_time_unit:
            return
            
        try:
            if self.is_paused:
                return

            # For simulated data or initial state
            if self.use_simulated_data:
                self.generate_simulated_data()

            # Make a thread-safe copy of the data
            with self.data_lock:
                # Skip if no data
                if (not self.dist_times and not self.lux_times) or \
                   (len(self.dist_times) == 0 and len(self.lux_times) == 0):
                    # Si no hay datos, crear al menos un punto para evitar gráficos vacíos
                    now = datetime.now()
                    if len(self.dist_times) == 0:
                        self.dist_times = [now]
                        self.dist_data = [0.0]
                    if len(self.lux_times) == 0:
                        self.lux_times = [now]
                        self.lux_data = [0.0]
                    
                # Copiamos los datos de cada sensor por separado
                dist_times = self.dist_times.copy() if self.dist_times else [datetime.now()]
                dist_data = self.dist_data.copy() if self.dist_data else [0.0]
                
                lux_times = self.lux_times.copy() if self.lux_times else [datetime.now()]
                lux_data = self.lux_data.copy() if self.lux_data else [0.0]
            
            # Clear previous plots
            self.ax_lux.clear()
            self.ax_dist.clear()

            # Set grid for both plots
            self.ax_lux.grid(True)
            self.ax_dist.grid(True)
            
            # Plot the light intensity data - asegurar que hay al menos un punto
            if lux_times and len(lux_times) > 0:
                try:
                    # Si solo hay un punto, duplicarlo para poder graficarlo
                    if len(lux_times) == 1:
                        lux_times = [lux_times[0], lux_times[0] + timedelta(seconds=1)]
                        lux_data = [lux_data[0], lux_data[0]]
                        
                    self.ax_lux.plot(lux_times, lux_data, label="Intensidad Lumínica (%)", 
                                     color="blue", marker="o", linestyle="-", markersize=4)
                    
                    # Mostrar intervalos explícitamente
                    interval_ms = self.calculate_real_sampling_time(self.t2_spinbox.value())
                    interval_text = f"Intervalo: {self.t2_spinbox.value()} {self.time_unit_combo.currentText()}"
                    self.ax_lux.text(0.02, 0.95, interval_text, transform=self.ax_lux.transAxes,
                                    fontsize=9, verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
                except Exception as e:
                    print(f"Error plotting light data: {e}")
                    import traceback
                    traceback.print_exc()
                
            # Plot the distance data - asegurar que hay al menos un punto
            if dist_times and len(dist_times) > 0:
                try:
                    # Si solo hay un punto, duplicarlo para poder graficarlo
                    if len(dist_times) == 1:
                        dist_times = [dist_times[0], dist_times[0] + timedelta(seconds=1)]
                        dist_data = [dist_data[0], dist_data[0]]
                        
                    self.ax_dist.plot(dist_times, dist_data, label="Distancia (cm)", 
                                     color="green", marker="o", linestyle="-", markersize=4)
                    
                    # Mostrar intervalos explícitamente
                    interval_ms = self.calculate_real_sampling_time(self.t1_spinbox.value())
                    interval_text = f"Intervalo: {self.t1_spinbox.value()} {self.time_unit_combo.currentText()}"
                    self.ax_dist.text(0.02, 0.95, interval_text, transform=self.ax_dist.transAxes,
                                    fontsize=9, verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
                except Exception as e:
                    print(f"Error plotting distance data: {e}")
                    import traceback
                    traceback.print_exc()
            
            # Set titles and labels
            self.ax_lux.set_title("Fotorresistencia - Intensidad Lumínica (%)")
            self.ax_lux.set_xlabel("Tiempo")
            self.ax_lux.set_ylabel("Intensidad Lumínica (%)")
            self.ax_lux.legend()
            
            self.ax_dist.set_title("Sharp - Distancia (cm)")
            self.ax_dist.set_xlabel("Tiempo")
            self.ax_dist.set_ylabel("Distancia (cm)")
            self.ax_dist.legend()
            
            # Format time axis for better readability based on selected time unit
            try:
                from matplotlib.dates import DateFormatter
                time_unit = self.time_unit_combo.currentText()
                
                # Choose appropriate time format based on selected unit
                if time_unit == "ms":
                    date_format = DateFormatter('%H:%M:%S.%f')  # Show milliseconds
                elif time_unit == "min":
                    date_format = DateFormatter('%H:%M')  # Show hours:minutes
                else:  # Default for seconds
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
                
            except Exception as e:
                print(f"Error formatting time axis: {e}")
            
            # Adjust y-axis to reduce visual spikes
            if len(lux_data) > 1:
                # Calculate sensible y-limits for light data with 10% padding
                lux_min = min(lux_data)
                lux_max = max(lux_data)
                lux_range = max(lux_max - lux_min, 1.0)  # Avoid division by zero
                self.ax_lux.set_ylim(
                    lux_min - (0.1 * lux_range), 
                    lux_max + (0.1 * lux_range)
                )
            
            if len(dist_data) > 1:
                # Calculate sensible y-limits for distance data with 10% padding
                dist_min = min(dist_data)
                dist_max = max(dist_data)
                dist_range = max(dist_max - dist_min, 1.0)  # Avoid division by zero
                self.ax_dist.set_ylim(
                    dist_min - (0.1 * dist_range), 
                    dist_max + (0.1 * dist_range)
                )
                
            # Auto-adjust spacing to prevent overlapping
            self.figure.tight_layout()
            
            # Log para depuración
            print(f"Update graphs: Plotting dist_data={len(dist_data)} points, lux_data={len(lux_data)} points")
            
            # Update the figure
            self.canvas.draw()
            
        except Exception as e:
            print(f"Error in update_graphs: {e}")
            import traceback
            traceback.print_exc()

    def generate_simulated_data(self):
        """Generate simulated data with precise timing to match the configured sampling rates."""
        # Don't generate data while time unit is changing
        if self.updating_time_unit:
            return
            
        try:
            now = datetime.now()
            
            # Crear puntos iniciales si es necesario
            if not self.dist_data or len(self.dist_data) == 0:
                with self.data_lock:
                    self.dist_data.append(75.0)  # Valor inicial razonable
                    self.dist_times.append(now)
                    
            if not self.lux_data or len(self.lux_data) == 0:
                with self.data_lock:
                    self.lux_data.append(50.0)  # Valor inicial razonable
                    self.lux_times.append(now)
            
            with self.data_lock:
                # Solo generamos datos de distancia cuando toca según el intervalo configurado
                if hasattr(self, 'next_t1_sample_time') and now >= self.next_t1_sample_time:
                    # Datos del sensor Sharp (distancia)
                    last_dist = self.dist_data[-1] if self.dist_data else 75.0
                    
                    # Determinamos la magnitud del cambio según la unidad de tiempo
                    time_unit = self.time_unit_combo.currentText()
                    if time_unit == "ms":
                        dist_change = random.uniform(-0.5, 0.5)
                    elif time_unit == "min":
                        dist_change = random.uniform(-3, 3)
                    else:  # segundos
                        dist_change = random.uniform(-1, 1)
                    
                    # Generamos el nuevo valor
                    new_dist = max(10, min(150, last_dist + dist_change))
                    
                    # Agregamos a los arrays específicos de distancia
                    self.dist_data.append(new_dist)
                    self.dist_times.append(now)
                    
                    # Actualizamos el valor actual
                    self.dist_value_label.setText(f"Valor Actual: {new_dist:.2f} cm")
                    
                    # Calculamos el siguiente tiempo de muestreo
                    self.next_t1_sample_time = self.next_t1_sample_time + timedelta(milliseconds=self.t1_interval_ms)
                    
                    # Si nos retrasamos, corregimos el próximo tiempo
                    if self.next_t1_sample_time < now:
                        self.next_t1_sample_time = now + timedelta(milliseconds=self.t1_interval_ms)
                    
                    print(f"T1: Generated distance data point: {new_dist:.2f} cm at {now.strftime('%H:%M:%S.%f')}")
                    print(f"T1: Next sample at: {self.next_t1_sample_time.strftime('%H:%M:%S.%f')}")
                
                # Solo generamos datos de luz cuando toca según el intervalo configurado
                if hasattr(self, 'next_t2_sample_time') and now >= self.next_t2_sample_time:
                    # Datos del sensor de luz
                    last_lux = self.lux_data[-1] if self.lux_data else 50.0
                    
                    # Determinamos la magnitud del cambio según la unidad de tiempo
                    time_unit = self.time_unit_combo.currentText()
                    if time_unit == "ms":
                        lux_change = random.uniform(-1, 1)
                    elif time_unit == "min":
                        lux_change = random.uniform(-5, 5)
                    else:  # segundos
                        lux_change = random.uniform(-2, 2)
                    
                    # Generamos el nuevo valor
                    new_lux = max(0, min(100, last_lux + lux_change))
                    
                    # Agregamos a los arrays específicos de luz
                    self.lux_data.append(new_lux)
                    self.lux_times.append(now)
                    
                    # Actualizamos el valor actual
                    self.lux_value_label.setText(f"Valor Actual: {new_lux:.2f} %")
                    
                    # Calculamos el siguiente tiempo de muestreo
                    self.next_t2_sample_time = self.next_t2_sample_time + timedelta(milliseconds=self.t2_interval_ms)
                    
                    # Si nos retrasamos, corregimos el próximo tiempo
                    if self.next_t2_sample_time < now:
                        self.next_t2_sample_time = now + timedelta(milliseconds=self.t2_interval_ms)
                    
                    print(f"T2: Generated light data point: {new_lux:.2f} % at {now.strftime('%H:%M:%S.%f')}")
                    print(f"T2: Next sample at: {self.next_t2_sample_time.strftime('%H:%M:%S.%f')}")
                
                # Limpiamos los datos antiguos basados en la unidad de tiempo
                time_unit = self.time_unit_combo.currentText()
                max_duration = timedelta(minutes=10) if time_unit == "min" else timedelta(seconds=60)
                
                # Limpiamos arrays de distancia
                while len(self.dist_times) > 1 and now - self.dist_times[0] > max_duration:
                    self.dist_times.pop(0)
                    self.dist_data.pop(0)
                
                # Limpiamos arrays de luz
                while len(self.lux_times) > 1 and now - self.lux_times[0] > max_duration:
                    self.lux_times.pop(0)
                    self.lux_data.pop(0)
                
                # Forzar al menos un punto inicial si no hay datos para mostrar
                if len(self.dist_data) == 0:
                    self.dist_data.append(75.0)  # Valor inicial razonable
                    self.dist_times.append(now)
                    
                if len(self.lux_data) == 0:
                    self.lux_data.append(50.0)  # Valor inicial razonable
                    self.lux_times.append(now)
                
        except Exception as e:
            print(f"Error generating simulated data: {e}")
            import traceback
            traceback.print_exc()

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
