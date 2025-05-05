import serial
import csv
import os
from datetime import datetime

REGISTRY_FILE = "epc_registry.csv"
LOG_FILE = "tag_log.csv"

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

def save_registry(registry):
    with open(REGISTRY_FILE, mode='w', newline='') as file:
        writer = csv.writer(file)
        for epc, custom_id in registry.items():
            writer.writerow([epc, custom_id])

def log_scan(custom_id, room_name):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logs = {}

    # Load existing logs
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, mode='r', newline='') as file:
            reader = csv.reader(file)
            for row in reader:
                if len(row) == 3:
                    _, name, _ = row
                    logs[name] = row

    # Update or insert
    logs[custom_id] = [timestamp, custom_id, room_name]

    # Write updated logs
    with open(LOG_FILE, mode='w', newline='') as file:
        writer = csv.writer(file)
        for row in logs.values():
            writer.writerow(row)

    return timestamp

def parse_epc(packet):
    if len(packet) < 23:
        return None
    epc_bytes = packet[3:15]
    epc = "".join("{:02X}".format(byte) for byte in epc_bytes)
    if len(epc) != 24:
        return None
    return epc

def main():
    registry = load_registry()
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

    print("📡 Listening for RFID packets on COM4...")

    try:
        while True:
            packet = ser.read(23)
            while len(packet) < 23:
                packet += ser.read(23 - len(packet))

            epc = parse_epc(packet)
            if epc:
                if epc in registry:
                    name = registry[epc]
                    print(f"✅ Detected: {name}")
                else:
                    print(f"🆕 New tag detected: {epc}")
                    name = input("Assign name to this tag: ")
                    registry[epc] = name
                    save_registry(registry)
                    print("✅ Tag saved.")

                room = input("Enter location (e.g., Be2 Lab): ")
                timestamp = log_scan(name, room)
                print(f"📝 Log updated: {timestamp}, {name}, {room}\n")
            else:
                print(f"❌ Incomplete or invalid data: {packet}")

    except KeyboardInterrupt:
        print("\n👋 Exiting.")
    finally:
        ser.close()

if __name__ == "__main__":
    main()
