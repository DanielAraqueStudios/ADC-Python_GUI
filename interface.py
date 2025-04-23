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
        self.setGeometry(100, 100, 1400, 1000)  # Ventana más grande para 4 gráficas

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
        self.temp_data = []      # Datos de temperatura
        self.temp_times = []     # Timestamps específicos para temperatura
        self.intensity_data = [] # Datos de intensidad lumínica (lux)
        self.intensity_times = []# Timestamps específicos para intensidad lumínica (lux)
        
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
        
        # Crear 4 subplots en una matriz 2x2
        self.ax_lux = self.figure.add_subplot(221)  # Arriba izquierda
        self.ax_dist = self.figure.add_subplot(222)  # Arriba derecha
        self.ax_temp = self.figure.add_subplot(223)  # Abajo izquierda
        self.ax_intensity = self.figure.add_subplot(224)  # Abajo derecha
        
        self.figure.subplots_adjust(hspace=0.5, wspace=0.3)  # Ajustar espaciado
        
        # Agregar grid a todas las gráficas
        self.ax_lux.grid(True)
        self.ax_dist.grid(True)
        self.ax_temp.grid(True)
        self.ax_intensity.grid(True)
        
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
            self.temp_times = []
            self.temp_data = []
            self.intensity_times = []
            self.intensity_data = []
            
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
        """Set initial labels and titles for all graphs."""
        # Limpiar todas las gráficas
        self.ax_lux.clear()
        self.ax_dist.clear()
        self.ax_temp.clear()
        self.ax_intensity.clear()
        
        # Asegurar que el grid esté visible en todas las gráficas
        self.ax_lux.grid(True)
        self.ax_dist.grid(True)
        self.ax_temp.grid(True)
        self.ax_intensity.grid(True)
        
        # Configurar cada gráfica
        self.ax_lux.set_title("Fotorresistencia - Intensidad Lumínica (%)")
        self.ax_lux.set_xlabel("Tiempo")
        self.ax_lux.set_ylabel("Intensidad Lumínica (%)")
        self.ax_lux.legend(["Intensidad Lumínica (%)"], loc="upper right")

        self.ax_dist.set_title("Sharp - Distancia (cm)")
        self.ax_dist.set_xlabel("Tiempo")
        self.ax_dist.set_ylabel("Distancia (cm)")
        self.ax_dist.legend(["Distancia (cm)"], loc="upper right")
        
        self.ax_temp.set_title("Temperatura (°C)")
        self.ax_temp.set_xlabel("Tiempo")
        self.ax_temp.set_ylabel("Temperatura (°C)")
        self.ax_temp.legend(["Temperatura"], loc="upper right")
        
        self.ax_intensity.set_title("Intensidad Lumínica (lux)")
        self.ax_intensity.set_xlabel("Tiempo")
        self.ax_intensity.set_ylabel("Intensidad (lux)")
        self.ax_intensity.legend(["Intensidad"], loc="upper right")

        self.canvas.draw()

    def update_graphs(self):
        """Update all graphs with thread-safety and debug output."""
        if self.updating_time_unit or self.is_paused:
            return

        try:
            if self.use_simulated_data:
                self.generate_simulated_data()

            # Hacer copia segura de los datos
            with self.data_lock:
                # Copiar datos existentes
                dist_times = self.dist_times.copy() if self.dist_times else [datetime.now()]
                dist_data = self.dist_data.copy() if self.dist_data else [0.0]
                lux_times = self.lux_times.copy() if self.lux_times else [datetime.now()]
                lux_data = self.lux_data.copy() if self.lux_data else [0.0]
                
                # Copiar nuevos datos
                temp_times = self.temp_times.copy() if self.temp_times else [datetime.now()]
                temp_data = self.temp_data.copy() if self.temp_data else [25.0]
                intensity_times = self.intensity_times.copy() if self.intensity_times else [datetime.now()]
                intensity_data = self.intensity_data.copy() if self.intensity_data else [500.0]

            # Limpiar todas las gráficas
            self.ax_lux.clear()
            self.ax_dist.clear()
            self.ax_temp.clear()
            self.ax_intensity.clear()

            # Configurar grid para todas las gráficas
            self.ax_lux.grid(True)
            self.ax_dist.grid(True)
            self.ax_temp.grid(True)
            self.ax_intensity.grid(True)

            # Plotear los datos existentes
            if lux_times and len(lux_times) > 0:
                if len(lux_times) == 1:
                    lux_times = [lux_times[0], lux_times[0] + timedelta(seconds=1)]
                    lux_data = [lux_data[0], lux_data[0]]
                self.ax_lux.plot(lux_times, lux_data, label="Intensidad Lumínica (%)", 
                                 color="blue", marker="o", linestyle="-", markersize=4)

            if dist_times and len(dist_times) > 0:
                if len(dist_times) == 1:
                    dist_times = [dist_times[0], dist_times[0] + timedelta(seconds=1)]
                    dist_data = [dist_data[0], dist_data[0]]
                self.ax_dist.plot(dist_times, dist_data, label="Distancia (cm)", 
                                  color="green", marker="o", linestyle="-", markersize=4)

            # Plotear nuevos datos
            if temp_times and len(temp_times) > 0:
                if len(temp_times) == 1:
                    temp_times = [temp_times[0], temp_times[0] + timedelta(seconds=1)]
                    temp_data = [temp_data[0], temp_data[0]]
                self.ax_temp.plot(temp_times, temp_data, label="Temperatura (°C)", 
                                  color="red", marker="o", linestyle="-", markersize=4)

            if intensity_times and len(intensity_times) > 0:
                if len(intensity_times) == 1:
                    intensity_times = [intensity_times[0], intensity_times[0] + timedelta(seconds=1)]
                    intensity_data = [intensity_data[0], intensity_data[0]]
                self.ax_intensity.plot(intensity_times, intensity_data, label="Intensidad (lux)", 
                                       color="purple", marker="o", linestyle="-", markersize=4)

            # Configurar títulos y etiquetas
            self.initialize_graph_labels()

            # Auto-ajustar diseño
            self.figure.tight_layout()
            
            # Actualizar canvas
            self.canvas.draw()

        except Exception as e:
            print(f"Error in update_graphs: {e}")
            import traceback
            traceback.print_exc()

    def generate_simulated_data(self):
        """Generate simulated data for all sensors."""
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
                
                # Generar datos de temperatura
                if not self.temp_data:
                    self.temp_data.append(25.0)
                    self.temp_times.append(now)
                last_temp = self.temp_data[-1]
                new_temp = max(15, min(35, last_temp + random.uniform(-0.5, 0.5)))
                self.temp_data.append(new_temp)
                self.temp_times.append(now)
                
                # Generar datos de intensidad lumínica
                if not self.intensity_data:
                    self.intensity_data.append(500.0)
                    self.intensity_times.append(now)
                last_intensity = self.intensity_data[-1]
                new_intensity = max(0, min(1000, last_intensity + random.uniform(-50, 50)))
                self.intensity_data.append(new_intensity)
                self.intensity_times.append(now)
                
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
                
                # Limpiamos arrays de temperatura
                while len(self.temp_times) > 1 and now - self.temp_times[0] > max_duration:
                    self.temp_times.pop(0)
                    self.temp_data.pop(0)
                
                # Limpiamos arrays de intensidad lumínica
                while len(self.intensity_times) > 1 and now - self.intensity_times[0] > max_duration:
                    self.intensity_times.pop(0)
                    self.intensity_data.pop(0)
                
        except Exception as e:
            print(f"Error generating simulated data: {e}")
            import traceback
            traceback.print_exc()

    def toggle_data_source(self):
        """Toggle between simulated and real data sources."""
        try:
            self.use_simulated_data = not self.use_simulated_data
            
            # Update button text
            self.toggle_data_button.setText("Modo: Simulado" if self.use_simulated_data else "Modo: Real")
            
            # Stop any current acquisition
            self.stop_acquisition()
            
            # Clear existing data
            with self.data_lock:
                self.dist_times = []
                self.lux_times = []
                self.dist_data = []
                self.lux_data = []
                self.temp_times = []
                self.temp_data = []
                self.intensity_times = []
                self.intensity_data = []
            
            # Update UI
            if self.use_simulated_data:
                self.connection_status.setText("Estado: Modo Simulado")
                self.connection_status.setStyleSheet("color: orange; font-weight: bold;")
                QMessageBox.information(self, "Modo de Datos", "Cambiado a datos simulados")
            else:
                self.connection_status.setText("Estado: Modo Real")
                self.connection_status.setStyleSheet("color: blue; font-weight: bold;")
                QMessageBox.information(self, "Modo de Datos", 
                    "Cambiado a datos reales.\nAsegúrese de seleccionar el puerto correcto.")
            
            # Reset graphs
            self.initialize_graph_labels()
            
        except Exception as e:
            print(f"Error toggling data source: {e}")
            self.connection_status.setText("Estado: Error")
            self.connection_status.setStyleSheet("color: red; font-weight: bold;")

    def update_time_unit(self):
        """Update the time unit for sampling."""
        # Prevent recursive calls or processing while already updating
        if self.updating_time_unit:
            return
            
        self.updating_time_unit = True
        try:
            # Get current unit selection
            new_unit = self.time_unit_combo.currentText()
            unit_map = {"ms": "m", "s": "s", "min": "M"}  # Map interface options to STM32 expected values
            unit = unit_map[new_unit]
            
            # Clear existing data when changing time units to prevent scale issues
            with self.data_lock:
                self.dist_times = []
                self.lux_times = []
                self.dist_data = []
                self.lux_data = []
                self.temp_times = []
                self.temp_data = []
                self.intensity_times = []
                self.intensity_data = []
            
            # Send to serial if connected
            if self.serial_conn and self.serial_conn.is_open:
                try:
                    # First send unit change
                    command = f"TU:{unit}\r\n"
                    self.serial_conn.write(command.encode())
                    time.sleep(0.1)  # Small delay to ensure processing
                    
                    # Then resend sampling times to ensure consistency
                    self.serial_conn.write(f"T1:{self.t1_spinbox.value()}\r\n".encode())
                    self.serial_conn.write(f"T2:{self.t2_spinbox.value()}\r\n".encode())
                except Exception as e:
                    print(f"Error sending time unit: {e}")
            
            # Update time labels
            self.update_time_labels()
            
            # Update simulation intervals if needed
            if hasattr(self, 't1_interval'):
                self.t1_interval = self.calculate_real_sampling_time(self.t1_spinbox.value())
                self.t1_interval_ms = self.t1_interval
            
            if hasattr(self, 't2_interval'):
                self.t2_interval = self.calculate_real_sampling_time(self.t2_spinbox.value())
                self.t2_interval_ms = self.t2_interval
            
            # Reset simulation next sampling times
            now = datetime.now()
            self.next_t1_sample_time = now
            self.next_t2_sample_time = now
            
        finally:
            # Always ensure we reset the flag
            self.updating_time_unit = False

    def update_time_labels(self):
        """Update time labels to reflect the current time unit."""
        unit_text = self.time_unit_combo.currentText()
        self.temp_real_time_label.setText(f"Tiempo Real: {self.t1_spinbox.value()} {unit_text}")
        self.light_real_time_label.setText(f"Tiempo Real: {self.t2_spinbox.value()} {unit_text}")

    def calculate_real_sampling_time(self, value):
        """Calculate real sampling time in milliseconds based on current time unit."""
        unit = self.time_unit_combo.currentText()
        if unit == "ms":
            return value
        elif unit == "s":
            return value * 1000
        elif unit == "min":
            return value * 60000
        return value * 1000  # Default to seconds if unknown unit

    def update_t1(self):
        """Update Sharp sensor sampling time."""
        try:
            value = self.t1_spinbox.value()
            
            # Update the real-time display
            unit_text = self.time_unit_combo.currentText()
            self.temp_real_time_label.setText(f"Tiempo Real: {value} {unit_text}")
            
            # Update simulation intervals if active
            self.t1_interval_ms = self.calculate_real_sampling_time(value)
            self.next_t1_sample_time = datetime.now()
            
            # Send to serial if connected
            if self.serial_conn and self.serial_conn.is_open:
                try:
                    command = f"T1:{value}\r\n"
                    self.serial_conn.write(command.encode())
                except Exception as e:
                    print(f"Error sending T1: {e}")

        except Exception as e:
            print(f"Error in update_t1: {e}")

    def update_t2(self):
        """Update light sensor sampling time."""
        try:
            value = self.t2_spinbox.value()
            
            # Update the real-time display
            unit_text = self.time_unit_combo.currentText()
            self.light_real_time_label.setText(f"Tiempo Real: {value} {unit_text}")
            
            # Update simulation intervals if active
            self.t2_interval_ms = self.calculate_real_sampling_time(value)
            self.next_t2_sample_time = datetime.now()
            
            # Send to serial if connected
            if self.serial_conn and self.serial_conn.is_open:
                try:
                    command = f"T2:{value}\r\n"
                    self.serial_conn.write(command.encode())
                except Exception as e:
                    print(f"Error sending T2: {e}")

        except Exception as e:
            print(f"Error in update_t2: {e}")

    def update_ft(self):
        """Update Sharp sensor filter setting."""
        try:
            value = self.ft_combo.currentIndex()
            if self.serial_conn and self.serial_conn.is_open:
                command = f"FT:{value}\r\n"
                self.serial_conn.write(command.encode())
        except Exception as e:
            print(f"Error in update_ft: {e}")

    def update_fl(self):
        """Update light sensor filter setting."""
        try:
            value = self.fl_combo.currentIndex()
            if self.serial_conn and self.serial_conn.is_open:
                command = f"FL:{value}\r\n"
                self.serial_conn.write(command.encode())
        except Exception as e:
            print(f"Error in update_fl: {e}")

    def update_st(self):
        """Update Sharp sensor filter sample count."""
        try:
            value = self.st_spinbox.value()
            if self.serial_conn and self.serial_conn.is_open:
                command = f"ST:{value}\r\n"
                self.serial_conn.write(command.encode())
        except Exception as e:
            print(f"Error in update_st: {e}")

    def update_sl(self):
        """Update light sensor filter sample count."""
        try:
            value = self.sl_spinbox.value()
            if self.serial_conn and self.serial_conn.is_open:
                command = f"SL:{value}\r\n"
                self.serial_conn.write(command.encode())
        except Exception as e:
            print(f"Error in update_sl: {e}")

    def start_acquisition(self):
        """Start data acquisition with improved error handling."""
        try:
            # Reset data buffers for clean start
            with self.data_lock:
                self.dist_times = []
                self.lux_times = []
                self.dist_data = []
                self.lux_data = []
                self.temp_times = []
                self.temp_data = []
                self.intensity_times = []
                self.intensity_data = []
            
            # Update UI
            self.connection_status.setText("Estado: Iniciando...")
            self.connection_status.setStyleSheet("color: orange; font-weight: bold;")
            QApplication.processEvents()
            
            # Calculate sampling intervals
            self.t1_interval_ms = self.calculate_real_sampling_time(self.t1_spinbox.value())
            self.t2_interval_ms = self.calculate_real_sampling_time(self.t2_spinbox.value())
            
            # Initialize sampling times
            now = datetime.now()
            self.last_t1_time = now
            self.last_t2_time = now
            self.next_t1_sample_time = now
            self.next_t2_sample_time = now
            
            # Start timer for UI updates
            if not self.timer.isActive():
                update_rate = 100  # Update UI every 100ms
                self.timer.start(update_rate)
            
            if not self.use_simulated_data:
                try:
                    # Connect to serial port if not using simulation
                    self.disconnect_serial()  # Ensure clean state
                    port = self.port_combo.currentText()
                    
                    if not port:
                        raise ValueError("No serial port selected")
                    
                    self.serial_conn = serial.Serial(
                        port=port,
                        baudrate=self.baud_rate,
                        timeout=0.5
                    )
                    
                    # Start read thread
                    self.running = True
                    self.serial_thread = threading.Thread(target=self.read_serial_data)
                    self.serial_thread.daemon = True
                    self.serial_thread.start()
                    
                    # Send start command
                    time.sleep(0.2)
                    self.serial_conn.write(b"a\r\n")
                    
                    self.connection_status.setText("Estado: Adquiriendo Datos")
                    self.connection_status.setStyleSheet("color: green; font-weight: bold;")
                    
                except Exception as e:
                    print(f"Error connecting to serial port: {e}")
                    self.use_simulated_data = True
                    self.connection_status.setText("Estado: Usando Simulación")
                    self.connection_status.setStyleSheet("color: orange; font-weight: bold;")
                    QMessageBox.warning(self, "Error de Conexión", 
                        f"Error conectando al puerto serial.\nCambiando a modo simulado.\n\nError: {str(e)}")
            
            else:
                self.connection_status.setText("Estado: Simulación Activa")
                self.connection_status.setStyleSheet("color: orange; font-weight: bold;")
            
        except Exception as e:
            print(f"Error in start_acquisition: {e}")
            self.connection_status.setText("Estado: Error")
            self.connection_status.setStyleSheet("color: red; font-weight: bold;")

    def stop_acquisition(self):
        """Stop data acquisition and clean up resources."""
        try:
            # Update UI
            self.connection_status.setText("Estado: Deteniendo...")
            self.connection_status.setStyleSheet("color: orange; font-weight: bold;")
            QApplication.processEvents()
            
            # Stop timer
            if self.timer.isActive():
                self.timer.stop()
            
            # Stop acquisition if using real hardware
            if self.serial_conn and self.serial_conn.is_open:
                try:
                    self.serial_conn.write(b"b\r\n")
                    time.sleep(0.2)
                except Exception as e:
                    print(f"Error sending stop command: {e}")
            
            # Clean up serial connection
            self.disconnect_serial()
            
            # Update UI
            self.connection_status.setText("Estado: Detenido")
            self.connection_status.setStyleSheet("color: red; font-weight: bold;")
            
        except Exception as e:
            print(f"Error in stop_acquisition: {e}")
            self.connection_status.setText("Estado: Error")
            self.connection_status.setStyleSheet("color: red; font-weight: bold;")

    def toggle_pause(self):
        """Toggle pause/resume state for graphs."""
        self.is_paused = not self.is_paused
        status = "Pausado" if self.is_paused else "Ejecutando"
        self.connection_status.setText(f"Estado: {status}")
        self.connection_status.setStyleSheet("color: orange; font-weight: bold;" if self.is_paused else "color: green; font-weight: bold;")

    def sync_all_settings(self):
        """Synchronize all settings with the STM32."""
        if not self.serial_conn or not self.serial_conn.is_open:
            QMessageBox.warning(self, "Advertencia", "No hay conexión serial activa.")
            return
            
        try:
            # Update UI to show sync in progress
            self.connection_status.setText("Estado: Sincronizando...")
            self.connection_status.setStyleSheet("color: orange; font-weight: bold;")
            QApplication.processEvents()
            
            # Send all settings in sequence
            commands = []
            
            # First send time unit
            unit_map = {"ms": "m", "s": "s", "min": "M"}
            unit = unit_map[self.time_unit_combo.currentText()]
            commands.append(f"TU:{unit}")
            
            # Sampling times
            commands.append(f"T1:{self.t1_spinbox.value()}")
            commands.append(f"T2:{self.t2_spinbox.value()}")
            
            # Filter settings
            commands.append(f"FT:{self.ft_combo.currentIndex()}")
            commands.append(f"FL:{self.fl_combo.currentIndex()}")
            commands.append(f"ST:{self.st_spinbox.value()}")
            commands.append(f"SL:{self.sl_spinbox.value()}")
            
            # Send each command with a small delay
            for cmd in commands:
                try:
                    self.serial_conn.write(f"{cmd}\r\n".encode())
                    print(f"Sent: {cmd}")
                    time.sleep(0.1)  # Small delay between commands
                except Exception as e:
                    print(f"Error sending command {cmd}: {e}")
                    raise
            
            # Request status to confirm settings
            self.serial_conn.write(b"STATUS\r\n")
            
            # Update UI to show success
            self.connection_status.setText("Estado: Sincronizado")
            self.connection_status.setStyleSheet("color: green; font-weight: bold;")
            QMessageBox.information(self, "Sincronización", "Configuración sincronizada correctamente")
            
        except Exception as e:
            print(f"Error en sincronización: {e}")
            self.connection_status.setText("Estado: Error de Sincronización")
            self.connection_status.setStyleSheet("color: red; font-weight: bold;")
            QMessageBox.critical(self, "Error", f"Error durante la sincronización:\n{str(e)}")

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


