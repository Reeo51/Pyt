import os
import sqlite3
import traceback

# Get the absolute path to the database
db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'instance', 'rfid.db')
print(f"Looking for database at: {db_path}")

# Check if the database exists at instance/rfid.db
if not os.path.exists(db_path):
    # Try another common location
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'rfid.db')
    print(f"Trying alternative location: {db_path}")

if not os.path.exists(db_path):
    print(f"Error: Database file not found at {db_path}")
    # List directories to help troubleshoot
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    print(f"Contents of {parent_dir}:")
    for item in os.listdir(parent_dir):
        print(f"  - {item}")
    exit(1)

print(f"Found database at {db_path}")

# Connect to the database
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Check if the tag table exists
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tag'")
if not cursor.fetchone():
    print("Error: 'tag' table does not exist in the database")
    print("Available tables:")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    for table in tables:
        print(f"  - {table[0]}")
    conn.close()
    exit(1)

# Get the columns in the tag table
cursor.execute(f"PRAGMA table_info(tag)")
columns = cursor.fetchall()
column_names = [column[1] for column in columns]
print(f"Current columns in tag table: {column_names}")

# Check if approved column already exists
if 'approved' in column_names:
    print("Column 'approved' already exists. No changes needed.")
else:
    # Add the approved column
    try:
        print("Attempting to add 'approved' column...")
        cursor.execute("ALTER TABLE tag ADD COLUMN approved BOOLEAN DEFAULT 0")
        conn.commit()
        print("Successfully added 'approved' column to tag table")
        
        # Verify the column was added
        cursor.execute(f"PRAGMA table_info(tag)")
        new_columns = cursor.fetchall()
        new_column_names = [column[1] for column in new_columns]
        print(f"Updated columns in tag table: {new_column_names}")
        
    except sqlite3.OperationalError as e:
        print(f"Error adding column: {e}")
        print(traceback.format_exc())

# Close the connection
conn.close() 