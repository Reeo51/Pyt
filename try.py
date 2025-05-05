import serial
import csv
import os
from datetime import datetime

REGISTRY_FILE = "epc_registry.csv"
LOG_FILE = "tag_log.csv"

# Load saved tag-to-ID registry
def load_registry():
    registry = {}
    if os.path.exists(REGISTRY_FILE):
        with open(REGISTRY_FILE, mode='r', newline='') as file:
            reader = csv.reader(file)
            for row in reader:
                if len(row) == 2:
                    epc, custom_id = row
                    registry[epc] = custom_id
    return registry

# Save the current registry to CSV
def save_registry(registry):
    with open(REGISTRY_FILE, mode='w', newline='') as file:
        writer = csv.writer(file)
        for epc, custom_id in registry.items():
            writer.writerow([epc, custom_id])

# Log scan event with timestamp and room info
def log_scan(custom_id, room_name):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, mode='a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([timestamp, custom_id, room_name])

# Parse EPC from packet with validity check
def parse_epc(packet):
    if len(packet) < 23:
        return None

    # Extract EPC bytes
    epc_bytes = packet[3:15]
    epc = "".join("{:02X}".format(byte) for byte in epc_bytes)

    # Check for valid EPC (e.g., length, correct format, etc.)
    if len(epc) != 24:  # EPC should be 24 hex characters
        return None

    # Additional check for non-tag values if needed
    if epc == "00F900D000D100F800F900D8":
        return None  # Example for ignoring specific non-tag response

    return epc

# Initialize serial port
ser = serial.Serial(
    port='COM4',
    baudrate=9600,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    bytesize=serial.EIGHTBITS,
    timeout=1
)

if not ser.is_open:
    ser.open()

epc_registry = load_registry()

print("Listening for RFID packets on COM4... Press Ctrl+C to exit.\n")

try:
    while True:
        # Try to read exactly 23 bytes
        packet = ser.read(23)
        while len(packet) < 23:
            packet += ser.read(23 - len(packet))

        print("Raw packet data:", packet)  # Debugging line to show the raw packet

        epc = parse_epc(packet)
        if epc:
            if epc in epc_registry:
                custom_id = epc_registry[epc]
                print(f"Detected: {custom_id}")
            else:
                print(f"New tag detected: {epc}")
                custom_id = input("Enter ID to assign to this tag (e.g., DMM01): ")
                epc_registry[epc] = custom_id
                save_registry(epc_registry)
                print(f"Assigned '{custom_id}' to tag {epc} and saved.")

            room = input("Enter room or location (e.g., Be2 Lab): ")
            log_scan(custom_id, room)
            print(f"Logged scan of '{custom_id}' at '{room}'\n")
        else:
            print(f"Incomplete or invalid data received: {packet}")

except KeyboardInterrupt:
    print("\nExiting...")
finally:
    ser.close()
