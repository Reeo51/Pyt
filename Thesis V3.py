import serial
import binascii
import time

# Configuration
PACKET_LENGTH = 23
HEADER_BYTE = b'\xCC'  # Your packet seems to start with 0xCC

# Set up the serial port
ser = serial.Serial(
    port='COM4', 
    baudrate=9600,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    bytesize=serial.EIGHTBITS,
    timeout=0.1  # Short timeout for more responsive buffering
)

# Restart the port if already open
if ser.is_open:
    ser.close()
ser.open()

buffer = bytearray()

try:
    while True:
        # Read and accumulate any available bytes
        if ser.in_waiting:
            data = ser.read(ser.in_waiting)
            buffer.extend(data)

        # Try to find the start of a packet
        start = buffer.find(HEADER_BYTE)
        # Only proceed if the header is found and enough bytes remain for a full packet
        if start != -1 and len(buffer) - start >= PACKET_LENGTH:
            # Extract a complete packet
            packet = buffer[start:start+PACKET_LENGTH]
            # Remove processed bytes from the buffer
            buffer = buffer[start+PACKET_LENGTH:]
            # Convert the packet to a hexadecimal string and print it
            hex_str = binascii.hexlify(packet).decode('utf-8').upper()
            print("RFID Data:", hex_str)
        
        # Brief sleep to avoid a busy loop
        time.sleep(0.05)
except KeyboardInterrupt:
    print("Exiting...")
finally:
    ser.close()
