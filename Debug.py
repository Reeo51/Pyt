#!/usr/bin/env python3
import subprocess
import csv
import os
import re
from datetime import datetime

# ── CONFIG ─────────────────────────────────────────────────────────────────────
EXE_PATH    = r"E:\Thesis\RFIDDemo3400\RFIDDemo.exe"  # path to your demo .exe
CSV_FILE    = 'tag_registry.csv'
ROOM_PROMPT = 'Enter location (e.g. Be2 Lab): '
# match a 96‑bit EPC (24 hex digits), adjust if your EPC is different length
EPC_RE      = re.compile(r'\b[0-9A-F]{24}\b')
# ────────────────────────────────────────────────────────────────────────────────

def load_registry():
    """Load EPC→name map from CSV_FILE."""
    reg = {}
    if os.path.exists(CSV_FILE):
        with open(CSV_FILE, newline='') as f:
            reader = csv.reader(f)
            for epc, name in reader:
                reg[epc] = name
    return reg

def save_registry(registry):
    """Save EPC→name map back to CSV_FILE."""
    with open(CSV_FILE, 'w', newline='') as f:
        writer = csv.writer(f)
        for epc, name in registry.items():
            writer.writerow([epc, name])

def log_scan(name, room):
    """Log the scan event to console (could be extended to file)."""
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"📝 {ts} | {name} @ {room}")

def main():
    # load existing mappings
    registry = load_registry()

    # launch the demo EXE and capture its stdout
    proc = subprocess.Popen(
        [EXE_PATH],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1  # line buffered
    )

    print(f"📡 Launched: {EXE_PATH}\nWaiting for RFID scans...\n")

    try:
        for raw_line in proc.stdout:
            line = raw_line.strip()
            if not line:
                continue

            # Debug: show raw output from the EXE
            print(f"⬇ RAW: {line}")

            # try to find a 24‑hex‑digit EPC in the line
            match = EPC_RE.search(line.upper())
            if not match:
                print("⚠️ No EPC found in this line.\n")
                continue

            epc = match.group(0)
            if epc in registry:
                name = registry[epc]
                print(f"✅ Known tag: {name}")
            else:
                print(f"🆕 New tag detected: {epc}")
                name = input("📝 Enter name for this tag: ").strip()
                registry[epc] = name
                save_registry(registry)
                print(f"✅ Saved '{name}'\n")

            room = input(ROOM_PROMPT).strip()
            log_scan(name, room)
            print()

    except KeyboardInterrupt:
        print("\n👋 Exiting.")
    finally:
        proc.terminate()
        proc.wait()

if __name__ == "__main__":
    main()
