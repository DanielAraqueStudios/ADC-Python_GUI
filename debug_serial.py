import serial
import time
import sys
import serial.tools.list_ports

def list_ports():
    """List all available serial ports."""
    ports = serial.tools.list_ports.comports()
    for i, port in enumerate(ports):
        print(f"{i}: {port.device} - {port.description}")
    return [p.device for p in ports]

def monitor_port(port, baudrate=9600, timeout=10):
    """Monitor a serial port for data."""
    try:
        print(f"Connecting to {port} at {baudrate} baud...")
        ser = serial.Serial(port=port, baudrate=baudrate, timeout=1)
        
        print(f"Connected to {port}. Monitoring for {timeout} seconds...")
        print(f"Press button on STM32 or send data...")
        
        start_time = time.time()
        while (time.time() - start_time) < timeout:
            if ser.in_waiting:
                data = ser.readline()
                try:
                    text = data.decode('latin1').strip()
                    print(f"Received: {text}")
                except:
                    print(f"Received raw: {data}")
                
                # Reset timeout on data received
                start_time = time.time()
            
            # Small delay to reduce CPU usage
            time.sleep(0.01)
            
        print("Monitoring completed.")
        ser.close()
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    print("Serial Port Debugging Tool")
    print("=========================")
    
    ports = list_ports()
    if not ports:
        print("No serial ports found!")
        sys.exit(1)
        
    print("\nChoose a port (enter number):")
    choice = input("> ")
    try:
        port = ports[int(choice)]
        monitor_port(port)
    except (ValueError, IndexError):
        print("Invalid selection. Exiting.")
