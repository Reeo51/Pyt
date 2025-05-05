import serial
import csv
from datetime import datetime
import time

COM_PORT = 'COM4'
BAUD_RATE = 9600
CSV_FILE = 'rfid_tags.csv'
last_logged_tag = None
last_log_time = 0
DEBOUNCE_SECONDS = 2

def log_rfid_data(tag_data):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(CSV_FILE, mode='a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([tag_data, timestamp])
    print(f"Logged: {tag_data} at {timestamp}")

def read_rfid_data():
    global last_logged_tag, last_log_time

    try:
        ser = serial.Serial(COM_PORT, BAUD_RATE, timeout=1)
        print(f"Listening on {COM_PORT} at {BAUD_RATE}...")

        while True:
            raw = ser.readline().strip()
            if not raw:
                continue

            try:
                tag = raw.decode('utf-8').strip()
            except:
                tag = raw.hex()

            now = time.time()
            if tag != last_logged_tag or now - last_log_time > DEBOUNCE_SECONDS:
                log_rfid_data(tag)
                last_logged_tag = tag
                last_log_time = now
            else:
                print(f"Ignored duplicate: {tag}")

    except serial.SerialException as e:
        print(f"[Serial Error] {e}")
    except Exception as e:
        print(f"[General Error] {e}")

if __name__ == "__main__":
    read_rfid_data()
