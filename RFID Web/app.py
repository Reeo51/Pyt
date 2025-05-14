from flask import Flask, render_template, redirect, url_for, request, flash, Response
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import UserMixin, LoginManager, login_user, login_required, current_user, logout_user
from flask_migrate import Migrate
from datetime import datetime, timedelta
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

# Set up Flask-Migrate
migrate = Migrate(app, db)

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
    last_changed_by = db.Column(db.String(120), nullable=True)

class InventoryTag(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rfid = db.Column(db.String(120), unique=True, nullable=False)
    label = db.Column(db.String(120), nullable=False)
    last_seen = db.Column(db.String(120), nullable=False)
    time_seen = db.Column(db.String(120), nullable=False)
    last_changed_by = db.Column(db.String(120), nullable=True)

# User loader
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# Autosave background task function
def autosave():
    while True:
        time.sleep(5)
        db.session.commit()
        print("Database autosaved.")

# Start autosave thread
def start_autosave():
    autosave_thread = threading.Thread(target=autosave)
    autosave_thread.daemon = True
    autosave_thread.start()

# Check inventory for missing items
def check_inventory():
    missing_items = []
    eight_hours_ago = datetime.now() - timedelta(hours=8)

    # Cross-check the tracking and inventory database
    inventory_tags = InventoryTag.query.all()
    tracking_tags = Tag.query.all()

    # Compare and find missing tags
    for tag in inventory_tags:
        if tag.rfid not in [t.rfid for t in tracking_tags]:
            missing_items.append(f"Missing from tracking: {tag.rfid} - {tag.label}")
        elif datetime.strptime(tag.time_seen, "%H:%M:%S") < eight_hours_ago:
            missing_items.append(f"Not scanned in the last 8 hours: {tag.rfid} - {tag.label}")

    if missing_items:
        for item in missing_items:
            flash(item, 'danger')  # Only show flash messages on the inventory check page
    else:
        flash("Inventory complete. No missing items.", 'success')

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
            return redirect(url_for('mode_selection'))  # Redirect to mode selection after successful login
        else:
            flash('Incorrect username or password. Please try again.', 'danger')

    return render_template('login.html')

@app.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    search_query = request.args.get('search')  

    if search_query:
        tags = Tag.query.filter(
            (Tag.rfid.like(f"%{search_query}%")) | 
            (Tag.label.like(f"%{search_query}%"))
        ).all()  
    else:
        tags = Tag.query.all()  

    if request.method == 'POST':
        rfid = request.form['rfid']
        label = request.form['label']
        time_now = datetime.now().strftime("%H:%M:%S")  

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

@app.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit(id):
    tag = Tag.query.get_or_404(id)

    if request.method == 'POST':
        tag.label = request.form['label']
        tag.last_seen = request.form['last_seen']
        tag.time_seen = datetime.now().strftime("%H:%M:%S")
        tag.last_changed_by = current_user.username  
        
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

@app.route('/events')
def events():
    def generate():
        with app.app_context():
            while True:
                tags = Tag.query.all()
                latest_tag = tags[-1] if tags else None
                if latest_tag:
                    yield f"data: {json.dumps({
                        'rfid': latest_tag.rfid,
                        'label': latest_tag.label,
                        'last_seen': latest_tag.last_seen,
                        'time_seen': latest_tag.time_seen,
                        'id': latest_tag.id
                    })}\n\n"
                time.sleep(1)

    return Response(generate(), content_type='text/event-stream')

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

@app.route('/mode_selection')
@login_required
def mode_selection():
    return render_template('mode_selection.html')  # Show mode selection page

@app.route('/inventory_check', methods=['GET', 'POST'])
@login_required
def inventory_check():
    search_query = request.args.get('search')  

    if search_query:
        inventory_tags = InventoryTag.query.filter(
            (InventoryTag.rfid.like(f"%{search_query}%")) | 
            (InventoryTag.label.like(f"%{search_query}%"))
        ).all()  
    else:
        inventory_tags = InventoryTag.query.all()  

    if request.method == 'POST':
        rfid = request.form['rfid']
        label = request.form['label']
        time_now = datetime.now().strftime("%H:%M:%S")  

        new_inventory_tag = InventoryTag(rfid=rfid, label=label, last_seen="Not yet scanned", time_seen=time_now)
        db.session.add(new_inventory_tag)
        db.session.commit()
        flash('Inventory RFID Tag added successfully!', 'success')
        return redirect(url_for('inventory_check'))

    check_inventory()  # Check inventory for missing items
    return render_template('inventory_check.html', inventory_tags=inventory_tags)


@app.route('/edit_inventory/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_inventory(id):
    tag = InventoryTag.query.get_or_404(id)

    if request.method == 'POST':
        tag.rfid = request.form['rfid']  # Update RFID
        tag.label = request.form['label']  # Update Label
        tag.last_changed_by = current_user.username
        tag.time_seen = datetime.now().strftime("%H:%M:%S")  # Update timestamp on change
        
        db.session.commit()
        flash('Inventory RFID Tag updated successfully!', 'success')
        return redirect(url_for('inventory_check'))

    return render_template('inventory_setup.html', tag=tag)


@app.route('/delete_inventory/<int:id>', methods=['GET', 'POST'])
@login_required
def delete_inventory(id):
    tag = InventoryTag.query.get_or_404(id)
    db.session.delete(tag)
    db.session.commit()
    flash('Inventory RFID Tag deleted successfully!', 'success')
    return redirect(url_for('inventory_check'))

def run_rfid_scanner():
    COM_PORT = 'COM4'  
    BAUD_RATE = 57600
    FLASK_URL = 'http://127.0.0.1:5000/scan'  

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
                        'location': 'Unknown Location'  
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

if __name__ == '__main__':
    start_autosave()  
    rfid_thread = threading.Thread(target=run_rfid_scanner)
    rfid_thread.daemon = True
    rfid_thread.start()
    app.run(debug=True, host='0.0.0.0', port=5000)
