import serial

def parse_epc(packet):
    if len(packet) < 16:
        return None
    epc_bytes = packet[3:15]
    epc = "".join("{:02X}".format(byte) for byte in epc_bytes)
    return epc

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

print("Listening for RFID packets on COM4...")

try:
    while True:
        packet = ser.read(16)
        if packet:
            epc = parse_epc(packet)
            if epc:
                print("Tag EPC:", epc)
            else:
                print("Incomplete data")
                print(packet)
except KeyboardInterrupt:
    print("Exiting...")
finally:
    ser.close()