import serial
import binascii
import re

COM_PORT = 'COM4'  # Change this to your correct COM port
BAUD_RATE = 57600

def extract_epcs(data):
    # Match EPC tags starting with E280 and are 24 hex characters long
    return re.findall(r'(E280[0-9A-F]{20})', data)

ser = serial.Serial(port=COM_PORT, baudrate=BAUD_RATE, timeout=1)
print(f"Connected to RFID Reader on {COM_PORT}")
print("Waiting for tag EPCs...\n")

try:
    while True:
        raw = ser.read(64)
        if raw:
            hex_data = binascii.hexlify(raw).decode('utf-8').upper()
            epcs = extract_epcs(hex_data)
            for epc in epcs:
                print(f"Detected Tag EPC: {epc}")

except KeyboardInterrupt:
    print("\nStopping...")
finally:
    ser.close()