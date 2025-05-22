import serial
import binascii
import re
import requests

# Set these parameters for each client
SERVER_IP = "192.168.1.X"  # Replace with your server's IP address
COM_PORT = "COM4"  # Change to the correct port for this PC
LOCATION = "Communication Lab"  # Give each scanner a unique name

def scan_and_send():
    ser = serial.Serial(port=COM_PORT, baudrate=57600, timeout=1)
    print(f"Connected to RFID reader on {COM_PORT}")
    
    while True:
        try:
            raw = ser.read(64)
            if raw:
                hex_data = binascii.hexlify(raw).decode('utf-8').upper()
                # Extract RFID tag IDs
                tags = re.findall(r'(E280[0-9A-F]{20})', hex_data)
                for tag in tags:
                    print(f"Detected tag: {tag}")
                    # Send to server
                    response = requests.post(f"http://{SERVER_IP}:5000/scan", 
                                           data={"rfid": tag, "location": LOCATION})
                    print(f"Server response: {response.status_code}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    scan_and_send()
