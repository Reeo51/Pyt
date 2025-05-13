from flask import Flask, render_template, redirect, url_for, request, flash, Response
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import UserMixin, LoginManager, login_user, login_required, current_user, logout_user
from datetime import datetime
import time
import json
import threading
import serial
import binascii
import re
import requests

app = Flask(__name__)
app.config['SECRET_KEY'] = 'mysecretkey'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///rfid.db'
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Database Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)

class Tag(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rfid = db.Column(db.String(120), unique=True, nullable=False)
    label = db.Column(db.String(120), nullable=False)
    last_seen = db.Column(db.String(120), nullable=False)
    time_seen = db.Column(db.String(120), nullable=False)

# User loader
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))  # Updated to use db.session.get()

# Routes
@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Login Unsuccessful. Please check username and password', 'danger')

    return render_template('login.html')

@app.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    search_query = request.args.get('search')  # Get the search query if any

    if search_query:
        tags = Tag.query.filter(
            (Tag.rfid.like(f"%{search_query}%")) | 
            (Tag.label.like(f"%{search_query}%"))
        ).all()  # Filter tags by RFID or Label
    else:
        tags = Tag.query.all()  # Get all tags if no search query

    if request.method == 'POST':
        rfid = request.form['rfid']
        label = request.form['label']
        time_now = datetime.now().strftime("%H:%M:%S")  # Get the current time

        new_tag = Tag(rfid=rfid, label=label, last_seen="Not yet scanned", time_seen=time_now)
        db.session.add(new_tag)
        db.session.commit()
        flash('RFID Tag added successfully!', 'success')
        return redirect(url_for('dashboard'))

    return render_template('dashboard.html', tags=tags)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        new_user = User(username=username, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        flash('Your account has been created!', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit(id):
    tag = Tag.query.get_or_404(id)

    if request.method == 'POST':
        tag.rfid = request.form['rfid']
        tag.label = request.form['label']
        tag.last_seen = request.form['location']
        tag.time_seen = datetime.now().strftime("%H:%M:%S")  # Save time when editing
        
        db.session.commit()
        flash('RFID Tag updated successfully!', 'success')
        return redirect(url_for('dashboard'))

    return render_template('edit.html', tag=tag)

@app.route('/delete/<int:id>', methods=['GET', 'POST'])
@login_required
def delete(id):
    tag = Tag.query.get_or_404(id)
    db.session.delete(tag)
    db.session.commit()
    flash('RFID Tag deleted successfully!', 'success')
    return redirect(url_for('dashboard'))

# SSE route to send updates to the client
@app.route('/events')
def events():
    def generate():
        # Use the app context to handle database queries
        with app.app_context():
            while True:
                # Query the latest RFID tag updates
                tags = Tag.query.all()
                # Send the latest tag as a JSON message
                latest_tag = tags[-1] if tags else None
                if latest_tag:
                    yield f"data: {json.dumps({
                        'rfid': latest_tag.rfid,
                        'label': latest_tag.label,
                        'last_seen': latest_tag.last_seen,
                        'time_seen': latest_tag.time_seen,
                        'id': latest_tag.id
                    })}\n\n"
                time.sleep(1)  # Adjust the frequency of updates

    return Response(generate(), content_type='text/event-stream')

# New route to handle RFID scan (data comes from your Unique ID.py script)
@app.route('/scan', methods=['POST'])
def scan_rfid():
    rfid = request.form.get('rfid')
    location = request.form.get('location')
    time_now = datetime.now().strftime("%H:%M:%S")
    
    tag = Tag.query.filter_by(rfid=rfid).first()
    if tag:
        tag.last_seen = location
        tag.time_seen = time_now
    else:
        tag = Tag(rfid=rfid, label="New Tag", last_seen=location, time_seen=time_now)
        db.session.add(tag)
    
    db.session.commit()

    return "RFID Tag processed successfully", 200

# Function to run RFID scanner in the background
def run_rfid_scanner():
    COM_PORT = 'COM4'  # Change this to your correct COM port
    BAUD_RATE = 57600
    FLASK_URL = 'http://127.0.0.1:5000/scan'  # URL to your Flask app's /scan route

    def extract_epcs(data):
        return re.findall(r'(E280[0-9A-F]{20})', data)

    ser = serial.Serial(port=COM_PORT, baudrate=BAUD_RATE, timeout=1)
    print(f"Connected to RFID Reader on {COM_PORT}")
    print("Waiting for tag EPCs...\n")

    try:
        while True:
            raw = ser.read(64)
            if raw:
                hex_data = binascii.hexlify(raw).decode('utf-8').upper()
                epcs = extract_epcs(hex_data)
                for epc in epcs:
                    print(f"Detected Tag EPC: {epc}")
                    data = {
                        'rfid': epc,
                        'location': 'Unknown Location'  # Placeholder for location
                    }
                    response = requests.post(FLASK_URL, data=data)
                    if response.status_code == 200:
                        print("RFID Tag processed successfully!")
                    else:
                        print(f"Failed to process RFID Tag: {response.status_code}")

    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        ser.close()

# Run the RFID scanner in a background thread
if __name__ == '__main__':
    rfid_thread = threading.Thread(target=run_rfid_scanner)
    rfid_thread.daemon = True
    rfid_thread.start()
    app.run(debug=True, host='0.0.0.0', port=5000)
