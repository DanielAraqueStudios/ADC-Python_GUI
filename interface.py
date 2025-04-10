import sys
import random
import serial
import threading
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QLabel, QPushButton, QComboBox, QMessageBox
from PyQt5.QtCore import QTimer
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import serial.tools.list_ports

class RealTimeGraph(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Real-Time Sensor Data")
        self.setGeometry(100, 100, 800, 600)

        # Serial connection
        self.serial_port = None
        self.baud_rate = 9600
        self.serial_conn = None
        self.use_simulated_data = True  # Flag to toggle between simulated and real data

        # Data buffers
        self.lux_data = []
        self.dist_data = []

        # Main layout
        self.main_widget = QWidget(self)
        self.setCentralWidget(self.main_widget)
        self.layout = QVBoxLayout(self.main_widget)

        # Graphs
        self.figure = Figure()
        self.canvas = FigureCanvas(self.figure)
        self.ax_lux = self.figure.add_subplot(211)
        self.ax_dist = self.figure.add_subplot(212)
        self.layout.addWidget(self.canvas)

        # Controls
        self.time_unit_label = QLabel("Time Unit:")
        self.time_unit_combo = QComboBox()
        self.time_unit_combo.addItems(["ms", "s", "min"])
        self.time_unit_combo.currentIndexChanged.connect(self.update_time_unit)

        self.start_button = QPushButton("Start")
        self.start_button.clicked.connect(self.start_acquisition)
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop_acquisition)

        self.port_label = QLabel("Select Port:")
        self.port_combo = QComboBox()
        self.refresh_ports()

        self.toggle_data_button = QPushButton("Toggle Data Source (Simulated/Real)")
        self.toggle_data_button.clicked.connect(self.toggle_data_source)

        self.layout.addWidget(self.time_unit_label)
        self.layout.addWidget(self.time_unit_combo)
        self.layout.addWidget(self.port_label)
        self.layout.addWidget(self.port_combo)
        self.layout.addWidget(self.toggle_data_button)
        self.layout.addWidget(self.start_button)
        self.layout.addWidget(self.stop_button)

        # Timer for updating graphs
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_graphs)

    def refresh_ports(self):
        self.port_combo.clear()
        ports = serial.tools.list_ports.comports()
        for port in ports:
            self.port_combo.addItem(port.device)

    def connect_serial(self):
        try:
            selected_port = self.port_combo.currentText()
            self.serial_conn = serial.Serial(selected_port, self.baud_rate, timeout=1)
            threading.Thread(target=self.read_serial_data, daemon=True).start()
        except serial.SerialException:
            QMessageBox.critical(self, "Error", "Unable to connect to the selected serial port.")

    def read_serial_data(self):
        while self.serial_conn and self.serial_conn.is_open:
            try:
                line = self.serial_conn.readline().decode().strip()
                if line.startswith("LUX:"):
                    self.lux_data.append(float(line.split(":")[1]))
                    if len(self.lux_data) > 50:
                        self.lux_data.pop(0)
                elif line.startswith("DIST:"):
                    self.dist_data.append(float(line.split(":")[1]))
                    if len(self.dist_data) > 50:
                        self.dist_data.pop(0)
            except Exception as e:
                print(f"Error reading serial data: {e}")

    def generate_simulated_data(self):
        self.lux_data.append(random.uniform(0, 1000))
        self.dist_data.append(random.uniform(10, 150))
        if len(self.lux_data) > 50:
            self.lux_data.pop(0)
        if len(self.dist_data) > 50:
            self.dist_data.pop(0)

    def toggle_data_source(self):
        self.use_simulated_data = not self.use_simulated_data
        source = "Simulated" if self.use_simulated_data else "Real"
        QMessageBox.information(self, "Data Source", f"Switched to {source} data source.")

    def update_time_unit(self):
        unit = self.time_unit_combo.currentText()
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.write(f"TU:{unit}\n".encode())

    def start_acquisition(self):
        if not self.use_simulated_data:
            self.connect_serial()
        self.timer.start(100)

    def stop_acquisition(self):
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
        self.timer.stop()

    def update_graphs(self):
        if self.use_simulated_data:
            self.generate_simulated_data()

        self.ax_lux.clear()
        self.ax_dist.clear()

        self.ax_lux.plot(self.lux_data, label="LUX (Light Intensity)", color="blue")
        self.ax_dist.plot(self.dist_data, label="DIST (Distance)", color="green")

        self.ax_lux.set_title("Light Intensity (LUX)")
        self.ax_dist.set_title("Distance (cm)")

        self.ax_lux.legend()
        self.ax_dist.legend()

        self.canvas.draw()

    def closeEvent(self, event):
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = RealTimeGraph()
    window.show()
    sys.exit(app.exec_())
