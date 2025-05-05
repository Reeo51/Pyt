from flask import Flask, render_template, request, redirect, url_for
import sqlite3

app = Flask(__name__)

def get_db_connection():
    conn = sqlite3.connect('rfid_library.db')
    conn.row_factory = sqlite3.Row
    return conn

# Home page — view and add tags
@app.route('/', methods=['GET', 'POST'])
def index():
    conn = get_db_connection()
    if request.method == 'POST':
        rfid = request.form['rfid']
        label = request.form['label']
        conn.execute('INSERT INTO tags (rfid, label) VALUES (?, ?)', (rfid, label))
        conn.commit()
    tags = conn.execute('SELECT * FROM tags').fetchall()
    conn.close()
    return render_template('index.html', tags=tags)

# Edit tag
@app.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit(id):
    conn = get_db_connection()
    tag = conn.execute('SELECT * FROM tags WHERE id = ?', (id,)).fetchone()
    if request.method == 'POST':
        new_label = request.form['label']
        conn.execute('UPDATE tags SET label = ? WHERE id = ?', (new_label, id))
        conn.commit()
        conn.close()
        return redirect(url_for('index'))
    conn.close()
    return render_template('edit.html', tag=tag)

# Delete tag
@app.route('/delete/<int:id>')
def delete(id):
    conn = get_db_connection()
    conn.execute('DELETE FROM tags WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

# Create table if not exists
def init_db():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rfid TEXT UNIQUE NOT NULL,
            label TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
