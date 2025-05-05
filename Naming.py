import sqlite3

def init_db():
    conn = sqlite3.connect('rfid_tags.db')
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

def add_tag(rfid, label):
    conn = sqlite3.connect('rfid_tags.db')
    c = conn.cursor()
    try:
        c.execute('INSERT INTO tags (rfid, label) VALUES (?, ?)', (rfid, label))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def get_tags():
    conn = sqlite3.connect('rfid_tags.db')
    c = conn.cursor()
    c.execute('SELECT * FROM tags')
    rows = c.fetchall()
    conn.close()
    return rows

def update_tag(rfid, new_label):
    conn = sqlite3.connect('rfid_tags.db')
    c = conn.cursor()
    c.execute('UPDATE tags SET label = ? WHERE rfid = ?', (new_label, rfid))
    conn.commit()
    conn.close()

def delete_tag(rfid):
    conn = sqlite3.connect('rfid_tags.db')
    c = conn.cursor()
    c.execute('DELETE FROM tags WHERE rfid = ?', (rfid,))
    conn.commit()
    conn.close()
