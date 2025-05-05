import sqlite3

# --- Database Setup ---
def init_db():
    conn = sqlite3.connect('rfid_library.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rfid TEXT UNIQUE NOT NULL,
            label TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

# --- CRUD Functions ---
def add_tag(rfid, label):
    conn = sqlite3.connect('rfid_library.db')
    c = conn.cursor()
    try:
        c.execute('INSERT INTO tags (rfid, label) VALUES (?, ?)', (rfid, label))
        conn.commit()
        print(f"Tag with RFID {rfid} added successfully!")
    except sqlite3.IntegrityError:
        print(f"Error: RFID {rfid} already exists.")
    finally:
        conn.close()

def view_tags():
    conn = sqlite3.connect('rfid_library.db')
    c = conn.cursor()
    c.execute('SELECT * FROM tags')
    rows = c.fetchall()
    if rows:
        for row in rows:
            print(f"RFID: {row[1]}, Label: {row[2]}")
    else:
        print("No tags found.")
    conn.close()

def update_tag(rfid, new_label):
    conn = sqlite3.connect('rfid_library.db')
    c = conn.cursor()
    c.execute('UPDATE tags SET label = ? WHERE rfid = ?', (new_label, rfid))
    conn.commit()
    print(f"Label for RFID {rfid} updated to {new_label}.")
    conn.close()

def delete_tag(rfid):
    conn = sqlite3.connect('rfid_library.db')
    c = conn.cursor()
    c.execute('DELETE FROM tags WHERE rfid = ?', (rfid,))
    conn.commit()
    print(f"Tag with RFID {rfid} deleted.")
    conn.close()

# --- User Interaction ---
def menu():
    print("\nRFID Library System")
    print("1. Add RFID")
    print("2. View all RFID tags")
    print("3. Update RFID label")
    print("4. Delete RFID")
    print("5. Exit")
    
    choice = input("Enter your choice: ")
    
    if choice == '1':
        rfid = input("Enter RFID: ")
        label = input("Enter Label: ")
        add_tag(rfid, label)
    elif choice == '2':
        view_tags()
    elif choice == '3':
        rfid = input("Enter RFID to update: ")
        new_label = input("Enter new label: ")
        update_tag(rfid, new_label)
    elif choice == '4':
        rfid = input("Enter RFID to delete: ")
        delete_tag(rfid)
    elif choice == '5':
        print("Exiting...")
        exit()
    else:
        print("Invalid choice, please try again.")

# --- Main ---
if __name__ == '__main__':
    init_db()
    while True:
        menu()
