from flask import Flask, render_template, redirect, url_for, request, flash, Response, jsonify, session, send_file
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
import os
import csv
import io
import sqlite3

app = Flask(__name__)
app.config['SECRET_KEY'] = 'mysecretkey'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///rfid.db'
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Global variables
inventory_mode_active = False

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
    date_seen = db.Column(db.String(120), nullable=True)
    last_changed_by = db.Column(db.String(120), nullable=True)
    approved = db.Column(db.Boolean, default=False, nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'rfid': self.rfid,
            'label': self.label,
            'last_seen': self.last_seen,
            'time_seen': self.time_seen,
            'date_seen': self.date_seen,
            'last_changed_by': self.last_changed_by,
            'approved': self.approved
        }

class InventoryTag(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rfid = db.Column(db.String(120), unique=True, nullable=False)
    label = db.Column(db.String(120), nullable=False)
    last_seen = db.Column(db.String(120), nullable=False)
    time_seen = db.Column(db.String(120), nullable=False)
    date_seen = db.Column(db.String(120), nullable=True)
    last_changed_by = db.Column(db.String(120), nullable=True)
    approved = db.Column(db.Boolean, default=False, nullable=False)

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
    time_missing_items = []
    time_warning_items = []
    current_time = datetime.now()
    eight_hours_ago = current_time - timedelta(hours=8)
    twenty_four_hours_ago = current_time - timedelta(hours=24)

    # Cross-check the tracking and inventory database
    inventory_tags = InventoryTag.query.all()
    tracking_tags = Tag.query.all()
    
    # Get lists of RFIDs from both systems
    inventory_rfids = [tag.rfid for tag in inventory_tags]
    tracking_rfids = [tag.rfid for tag in tracking_tags]

    # Find tracking items missing from inventory
    for tag in tracking_tags:
        if tag.rfid not in inventory_rfids:
            missing_items.append(f"Missing from inventory: {tag.rfid} - {tag.label}")
        
        # Check if item hasn't been scanned in 8+ hours
        try:
            # If date_seen is available, use it for accurate comparison
            if tag.date_seen:
                last_seen_datetime = datetime.strptime(f"{tag.date_seen} {tag.time_seen}", "%Y-%m-%d %H:%M:%S")
                time_diff = current_time - last_seen_datetime
                hours_diff = time_diff.total_seconds() / 3600  # Convert to hours
                
                if hours_diff >= 24:  # Missing if not scanned for 24+ hours
                    time_missing_items.append(f"Not scanned in {int(hours_diff)} hours: {tag.rfid} - {tag.label} (Last seen: {tag.date_seen} {tag.time_seen})")
                elif hours_diff >= 8:  # Warning if not scanned for 8+ hours
                    time_warning_items.append(f"Not scanned in {int(hours_diff)} hours: {tag.rfid} - {tag.label} (Last seen: {tag.date_seen} {tag.time_seen})")
            else:
                # Fall back to the old method if date_seen is not available
                last_seen_time = datetime.strptime(tag.time_seen, "%H:%M:%S")
                # Set date to today for comparison
                last_seen_time = last_seen_time.replace(
                    year=current_time.year,
                    month=current_time.month,
                    day=current_time.day
                )
                
                # If time is in future, it was from yesterday (or earlier)
                if last_seen_time > current_time:
                    last_seen_time = last_seen_time.replace(day=last_seen_time.day - 1)
                
                time_diff = current_time - last_seen_time
                hours_diff = time_diff.total_seconds() / 3600  # Convert to hours
                
                if hours_diff >= 8:
                    time_warning_items.append(f"Not scanned in {int(hours_diff)} hours: {tag.rfid} - {tag.label} (Last seen time: {tag.time_seen})")
        except ValueError:
            # Skip items with invalid time format
            pass

    # Find inventory items missing from tracking (should be rare)
    for tag in inventory_tags:
        if tag.rfid not in tracking_rfids:
            missing_items.append(f"In inventory but not tracked: {tag.rfid} - {tag.label}")

    # Show flash messages for physically missing items
    if missing_items:
        for item in missing_items:
            flash(item, 'danger')  # Show flash messages for missing items
    
    # Show flash messages for time-based missing items
    if time_missing_items:
        for item in time_missing_items:
            flash(item, 'danger')  # Critical - missing for 24+ hours
    
    # Show flash messages for time-based warning items
    if time_warning_items:
        for item in time_warning_items:
            flash(item, 'warning')  # Warning - not scanned in 8+ hours
    
    # Return missing and time_missing items for use in the template
    return {
        'missing_rfids': [tag.rfid for tag in tracking_tags if tag.rfid not in inventory_rfids],
        'time_warning_rfids': [tag.rfid for tag in tracking_tags if is_time_warning(tag, eight_hours_ago, twenty_four_hours_ago)],
        'time_missing_rfids': [tag.rfid for tag in tracking_tags if is_time_missing(tag, twenty_four_hours_ago)]
    }

# Helper function to check if an item is time-missing (not scanned in 24+ hours)
def is_time_missing(tag, twenty_four_hours_ago):
    try:
        current_time = datetime.now()
        
        # If date_seen is available, use it for accurate comparison
        if tag.date_seen:
            last_seen_datetime = datetime.strptime(f"{tag.date_seen} {tag.time_seen}", "%Y-%m-%d %H:%M:%S")
            return last_seen_datetime < twenty_four_hours_ago
        
        # Fall back to the old method if date_seen is not available
        last_seen_time = datetime.strptime(tag.time_seen, "%H:%M:%S")
        # Set date to today for comparison
        last_seen_time = last_seen_time.replace(
            year=current_time.year, 
            month=current_time.month,
            day=current_time.day
        )
        
        # If time is in future, it was from yesterday (or earlier)
        if last_seen_time > current_time:
            last_seen_time = last_seen_time.replace(day=last_seen_time.day - 1)
        
        # Check if it's more than 24 hours ago
        return last_seen_time < twenty_four_hours_ago
    except ValueError:
        return False  # In case of invalid time format

# Helper function to check if an item has not been scanned in 8+ hours but less than 24 hours
def is_time_warning(tag, eight_hours_ago, twenty_four_hours_ago):
    try:
        current_time = datetime.now()
        
        # If date_seen is available, use it for accurate comparison
        if tag.date_seen:
            last_seen_datetime = datetime.strptime(f"{tag.date_seen} {tag.time_seen}", "%Y-%m-%d %H:%M:%S")
            return eight_hours_ago > last_seen_datetime >= twenty_four_hours_ago
        
        # Fall back to the old method if date_seen is not available
        last_seen_time = datetime.strptime(tag.time_seen, "%H:%M:%S")
        # Set date to today for comparison
        last_seen_time = last_seen_time.replace(
            year=current_time.year, 
            month=current_time.month,
            day=current_time.day
        )
        
        # If time is in future, it was from yesterday (or earlier)
        if last_seen_time > current_time:
            last_seen_time = last_seen_time.replace(day=last_seen_time.day - 1)
        
        # Check if it's between 8 and 24 hours ago
        return eight_hours_ago > last_seen_time >= twenty_four_hours_ago
    except ValueError:
        return False  # In case of invalid time format

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

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        user = User.query.filter_by(username=username).first()
        
        if user:
            flash('Username already exists. Please choose a different username.', 'danger')
        else:
            new_user = User(username=username, password=hashed_password)
            db.session.add(new_user)
            db.session.commit()
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))

    return render_template('register.html')

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
        date_now = datetime.now().strftime("%Y-%m-%d")

        new_tag = Tag(rfid=rfid, label=label, last_seen="Not yet scanned", time_seen=time_now, date_seen=date_now)
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
        tag.date_seen = datetime.now().strftime("%Y-%m-%d")
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
    location = request.form.get('location', 'Unknown')  # Get location from the request
    time_now = datetime.now().strftime("%H:%M:%S")
    date_now = datetime.now().strftime("%Y-%m-%d")
    
    tag = Tag.query.filter_by(rfid=rfid).first()
    if tag:
        tag.last_seen = location
        tag.time_seen = time_now
        tag.date_seen = date_now
    else:
        tag = Tag(rfid=rfid, label="New Tag", last_seen=location, time_seen=time_now, date_seen=date_now)
        db.session.add(tag)
    
    db.session.commit()

    return "RFID Tag processed successfully", 200

@app.route('/mode_selection')
@login_required
def mode_selection():
    return render_template('mode_selection.html')

@app.route('/inventory_check', methods=['GET'])
@login_required
def inventory_check():
    # Get all inventory tags to extract RFIDs for comparison
    inventory_tags = InventoryTag.query.all()
    inventory_rfids = [tag.rfid for tag in inventory_tags]
    
    # Get all tracking tags without filtering
    tracking_tags = Tag.query.all()  

    # Check inventory for missing items and get missing status
    missing_status = check_inventory()
    
    return render_template('inventory_check.html', 
                          tracking_tags=tracking_tags,
                          inventory_rfids=inventory_rfids,
                          missing_rfids=missing_status['missing_rfids'],
                          time_warning_rfids=missing_status['time_warning_rfids'],
                          time_missing_rfids=missing_status['time_missing_rfids'])

@app.route('/start_inventory', methods=['POST'])
@login_required
def start_inventory():
    # Get search parameters from the request
    data = request.json
    search_term = data.get('search_term', '')
    
    # Prepare messages list for JSON response
    messages = []
    
    if search_term:
        # Search for tags matching either RFID or label
        tracking_tags = Tag.query.filter(
            (Tag.rfid.like(f"%{search_term}%")) | 
            (Tag.label.like(f"%{search_term}%"))
        ).all()
        
        if tracking_tags:
            # Calculate time since last scan for each tag
            current_time = datetime.now()
            for tag in tracking_tags:
                # Parse the time_seen string to get a datetime object
                try:
                    if tag.date_seen:
                        # Use date_seen if available
                        last_seen_datetime = datetime.strptime(f"{tag.date_seen} {tag.time_seen}", "%Y-%m-%d %H:%M:%S")
                        time_diff = current_time - last_seen_datetime
                        hours, remainder = divmod(time_diff.total_seconds(), 3600)
                        minutes, seconds = divmod(remainder, 60)
                        
                        time_diff_str = f"{int(hours)} hours, {minutes} minutes since last scan"
                        
                        # Create message with all required information including date
                        message_text = f"Found: RFID: {tag.rfid}, Label: {tag.label}, Location: {tag.last_seen}, Last seen: {tag.date_seen} {tag.time_seen} ({time_diff_str})"
                    else:
                        # Fall back to time only if date not available
                        last_seen_time = datetime.strptime(tag.time_seen, "%H:%M:%S")
                        # Set date to today for comparison
                        last_seen_time = last_seen_time.replace(
                            year=current_time.year, 
                            month=current_time.month, 
                            day=current_time.day
                        )
                        
                        # If the time is in the future, it means the scan was from yesterday
                        if last_seen_time > current_time:
                            last_seen_time = last_seen_time.replace(day=last_seen_time.day - 1)
                            
                        # Calculate time difference
                        time_diff = current_time - last_seen_time
                        hours, remainder = divmod(time_diff.seconds, 3600)
                        minutes, seconds = divmod(remainder, 60)
                        
                        time_diff_str = f"{hours} hours, {minutes} minutes since last scan"
                        
                        # Create message with all required information
                        message_text = f"Found: RFID: {tag.rfid}, Label: {tag.label}, Location: {tag.last_seen}, {time_diff_str}"
                    
                    messages.append({
                        'category': 'success',
                        'message': message_text
                    })
                    
                    # Also create a flash message for compatibility
                    flash(message_text, "success")
                
                except ValueError:
                    # Handle case where time_seen is not in the expected format
                    date_info = f", Date: {tag.date_seen}" if tag.date_seen else ""
                    message_text = f"Found: RFID: {tag.rfid}, Label: {tag.label}, Location: {tag.last_seen}, Time: {tag.time_seen}{date_info}"
                    messages.append({
                        'category': 'success',
                        'message': message_text
                    })
                    
                    # Also create a flash message for compatibility
                    flash(message_text, "success")
        else:
            message_text = f"No items found matching '{search_term}'"
            messages.append({
                'category': 'warning',
                'message': message_text
            })
            
            # Also create a flash message for compatibility
            flash(message_text, "warning")
    
    # Set inventory mode active
    global inventory_mode_active
    inventory_mode_active = True
    
    return jsonify({
        'status': 'success', 
        'message': 'Inventory search complete',
        'messages': messages
    })

@app.route('/finish_inventory', methods=['POST'])
@login_required
def finish_inventory():
    # This route handles the completion of inventory mode
    global inventory_mode_active
    inventory_mode_active = False
    
    # Run the inventory check to update missing items
    check_inventory()
    
    return jsonify({'status': 'success', 'message': 'Inventory completed'})

@app.route('/edit_inventory/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_inventory(id):
    tag = InventoryTag.query.get_or_404(id)

    if request.method == 'POST':
        tag.rfid = request.form['rfid']  # Update RFID
        tag.label = request.form['label']  # Update Label
        tag.last_changed_by = current_user.username
        tag.time_seen = datetime.now().strftime("%H:%M:%S")  # Update timestamp on change
        tag.date_seen = datetime.now().strftime("%Y-%m-%d")  # Update date on change
        
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

@app.route('/sync_inventory')
@login_required
def sync_inventory():
    # Get all tracking tags
    tracking_tags = Tag.query.all()
    
    # Get all inventory tags to get existing RFIDs
    inventory_tags = InventoryTag.query.all()
    inventory_rfids = [tag.rfid for tag in inventory_tags]
    
    # Count of newly added items
    added_count = 0
    
    # Add tracking tags to inventory if not already there
    for tag in tracking_tags:
        if tag.rfid not in inventory_rfids:
            # Create new inventory entry based on tracking tag
            new_inventory_tag = InventoryTag(
                rfid=tag.rfid,
                label=tag.label,
                last_seen=tag.last_seen,
                time_seen=tag.time_seen,
                date_seen=tag.date_seen,
                last_changed_by=current_user.username
            )
            db.session.add(new_inventory_tag)
            added_count += 1
    
    # Commit changes to database
    db.session.commit()
    
    if added_count > 0:
        flash(f"Successfully synchronized inventory. Added {added_count} new items.", "success")
    else:
        flash("Inventory is already synchronized with tracking system.", "info")
    
    return redirect(url_for('inventory_check'))

def run_rfid_scanner_com3():
    COM_PORT = 'COM3'  
    BAUD_RATE = 57600
    FLASK_URL = 'http://127.0.0.1:5000/scan'  
    LOCATION = 'Instrumentation Laboratory'

    def extract_epcs(data):
        return re.findall(r'(E280[0-9A-F]{20})', data)

    ser = serial.Serial(port=COM_PORT, baudrate=BAUD_RATE, timeout=1)
    print(f"Connected to RFID Reader on {COM_PORT} for {LOCATION}")
    print("Waiting for tag EPCs...\n")

    try:
        while True:
            raw = ser.read(64)
            if raw:
                hex_data = binascii.hexlify(raw).decode('utf-8').upper()
                epcs = extract_epcs(hex_data)
                for epc in epcs:
                    print(f"Detected Tag EPC: {epc} in {LOCATION}")
                    data = {
                        'rfid': epc,
                        'location': LOCATION
                    }
                    response = requests.post(FLASK_URL, data=data)
                    if response.status_code == 200:
                        print(f"RFID Tag processed successfully from {LOCATION}!")
                    else:
                        print(f"Failed to process RFID Tag from {LOCATION}: {response.status_code}")

    except KeyboardInterrupt:
        print(f"\nStopping {LOCATION} scanner...") 
    finally:
        ser.close()

def run_rfid_scanner_com4():
    COM_PORT = 'COM4'  
    BAUD_RATE = 57600
    FLASK_URL = 'http://127.0.0.1:5000/scan'  
    LOCATION = 'Communication Laboratory'

    def extract_epcs(data):
        return re.findall(r'(E280[0-9A-F]{20})', data)

    ser = serial.Serial(port=COM_PORT, baudrate=BAUD_RATE, timeout=1)
    print(f"Connected to RFID Reader on {COM_PORT} for {LOCATION}")
    print("Waiting for tag EPCs...\n")

    try:
        while True:
            raw = ser.read(64)
            if raw:
                hex_data = binascii.hexlify(raw).decode('utf-8').upper()
                epcs = extract_epcs(hex_data)
                for epc in epcs:
                    print(f"Detected Tag EPC: {epc} in {LOCATION}")
                    data = {
                        'rfid': epc,
                        'location': LOCATION
                    }
                    response = requests.post(FLASK_URL, data=data)
                    if response.status_code == 200:
                        print(f"RFID Tag processed successfully from {LOCATION}!")
                    else:
                        print(f"Failed to process RFID Tag from {LOCATION}: {response.status_code}")

    except KeyboardInterrupt:
        print(f"\nStopping {LOCATION} scanner...") 
    finally:
        ser.close()

def run_rfid_scanner_com5():
    COM_PORT = 'COM5'  
    BAUD_RATE = 57600
    FLASK_URL = 'http://127.0.0.1:5000/scan'  
    LOCATION = 'Electronics Laboratory'

    def extract_epcs(data):
        return re.findall(r'(E280[0-9A-F]{20})', data)

    ser = serial.Serial(port=COM_PORT, baudrate=BAUD_RATE, timeout=1)
    print(f"Connected to RFID Reader on {COM_PORT} for {LOCATION}")
    print("Waiting for tag EPCs...\n")

    try:
        while True:
            raw = ser.read(64)
            if raw:
                hex_data = binascii.hexlify(raw).decode('utf-8').upper()
                epcs = extract_epcs(hex_data)
                for epc in epcs:
                    print(f"Detected Tag EPC: {epc} in {LOCATION}")
                    data = {
                        'rfid': epc,
                        'location': LOCATION
                    }
                    response = requests.post(FLASK_URL, data=data)
                    if response.status_code == 200:
                        print(f"RFID Tag processed successfully from {LOCATION}!")
                    else:
                        print(f"Failed to process RFID Tag from {LOCATION}: {response.status_code}")

    except KeyboardInterrupt:
        print(f"\nStopping {LOCATION} scanner...") 
    finally:
        ser.close()

def run_rfid_scanner_com6():
    COM_PORT = 'COM6'  
    BAUD_RATE = 57600
    FLASK_URL = 'http://127.0.0.1:5000/scan'  
    LOCATION = 'Research Laboratory'

    def extract_epcs(data):
        return re.findall(r'(E280[0-9A-F]{20})', data)

    ser = serial.Serial(port=COM_PORT, baudrate=BAUD_RATE, timeout=1)
    print(f"Connected to RFID Reader on {COM_PORT} for {LOCATION}")
    print("Waiting for tag EPCs...\n")

    try:
        while True:
            raw = ser.read(64)
            if raw:
                hex_data = binascii.hexlify(raw).decode('utf-8').upper()
                epcs = extract_epcs(hex_data)
                for epc in epcs:
                    print(f"Detected Tag EPC: {epc} in {LOCATION}")
                    data = {
                        'rfid': epc,
                        'location': LOCATION
                    }
                    response = requests.post(FLASK_URL, data=data)
                    if response.status_code == 200:
                        print(f"RFID Tag processed successfully from {LOCATION}!")
                    else:
                        print(f"Failed to process RFID Tag from {LOCATION}: {response.status_code}")

    except KeyboardInterrupt:
        print(f"\nStopping {LOCATION} scanner...") 
    finally:
        ser.close()

@app.route('/toggle_approval/<int:id>', methods=['POST'])
@login_required
def toggle_approval(id):
    tag = Tag.query.get_or_404(id)
    tag.approved = not tag.approved
    tag.last_changed_by = current_user.username
    db.session.commit()
    return jsonify({
        'status': 'success',
        'approved': tag.approved,
        'last_changed_by': tag.last_changed_by,
        'message': f'Tag {tag.rfid} has been {"approved" if tag.approved else "unapproved"}'
    })

@app.route('/clear_messages', methods=['POST'])
@login_required
def clear_messages():
    # Clear all flash messages stored in the session
    session['_flashes'] = []
    return jsonify({'status': 'success'})

@app.route('/database/backup')
@login_required
def backup_database():
    try:
        # Create a backup of the database
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f'rfid_backup_{timestamp}.db'
        
        # Connect to the current database
        source = sqlite3.connect(app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', ''))
        
        # Create a backup file
        backup_path = os.path.join('backups', backup_filename)
        os.makedirs('backups', exist_ok=True)
        
        # Copy the database to the backup file
        backup = sqlite3.connect(backup_path)
        source.backup(backup)
        
        # Close the connections
        backup.close()
        source.close()
        
        # Prepare the backup file for download
        return send_file(
            backup_path,
            as_attachment=True,
            download_name=backup_filename,
            mimetype='application/x-sqlite3'
        )
        
    except Exception as e:
        flash(f'Error creating backup: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))

@app.route('/export/tags/csv')
@login_required
def export_tags_csv():
    try:
        # Create a StringIO object to write CSV data
        si = io.StringIO()
        cw = csv.writer(si)
        
        # Write headers
        cw.writerow(['RFID', 'Label', 'Last Seen', 'Time Seen', 'Date Seen', 'Last Changed By', 'Approved'])
        
        # Write data
        tags = Tag.query.all()
        for tag in tags:
            cw.writerow([
                tag.rfid,
                tag.label,
                tag.last_seen,
                tag.time_seen,
                tag.date_seen or '',
                tag.last_changed_by or '',
                'Yes' if tag.approved else 'No'
            ])
        
        # Prepare the response
        output = si.getvalue()
        si.close()
        
        return Response(
            output,
            mimetype='text/csv',
            headers={
                'Content-Disposition': 'attachment; filename=rfid_tags.csv',
                'Content-Type': 'text/csv'
            }
        )
        
    except Exception as e:
        flash(f'Error exporting CSV: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))

@app.route('/import/tags/csv', methods=['GET', 'POST'])
@login_required
def import_tags_csv():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file uploaded', 'danger')
            return redirect(request.url)
        
        file = request.files['file']
        if file.filename == '':
            flash('No file selected', 'danger')
            return redirect(request.url)
        
        if not file.filename.endswith('.csv'):
            flash('Please upload a CSV file', 'danger')
            return redirect(request.url)
        
        try:
            # Read the CSV file
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            csv_input = csv.reader(stream)
            
            # Skip header row
            next(csv_input)
            
            # Process each row
            success_count = 0
            error_count = 0
            
            for row in csv_input:
                try:
                    if len(row) >= 7:  # Ensure we have all required fields
                        rfid = row[0]
                        label = row[1]
                        last_seen = row[2]
                        time_seen = row[3]
                        date_seen = row[4] if row[4] else None
                        last_changed_by = row[5] if row[5] else None
                        approved = row[6].lower() == 'yes'
                        
                        # Check if tag already exists
                        tag = Tag.query.filter_by(rfid=rfid).first()
                        if tag:
                            # Update existing tag
                            tag.label = label
                            tag.last_seen = last_seen
                            tag.time_seen = time_seen
                            tag.date_seen = date_seen
                            tag.last_changed_by = current_user.username
                            tag.approved = approved
                        else:
                            # Create new tag
                            tag = Tag(
                                rfid=rfid,
                                label=label,
                                last_seen=last_seen,
                                time_seen=time_seen,
                                date_seen=date_seen,
                                last_changed_by=current_user.username,
                                approved=approved
                            )
                            db.session.add(tag)
                        
                        success_count += 1
                    else:
                        error_count += 1
                        
                except Exception as e:
                    error_count += 1
                    continue
            
            db.session.commit()
            
            if success_count > 0:
                flash(f'Successfully imported {success_count} tags', 'success')
            if error_count > 0:
                flash(f'Failed to import {error_count} tags', 'warning')
                
        except Exception as e:
            flash(f'Error processing CSV file: {str(e)}', 'danger')
        
        return redirect(url_for('dashboard'))
    
    return render_template('import_csv.html')

@app.route('/search/advanced', methods=['GET', 'POST'])
@login_required
def advanced_search():
    if request.method == 'POST':
        # Get search parameters
        rfid = request.form.get('rfid', '')
        label = request.form.get('label', '')
        location = request.form.get('location', '')
        approval_status = request.form.get('approval_status', '')
        date_from = request.form.get('date_from', '')
        date_to = request.form.get('date_to', '')
        
        # Build query
        query = Tag.query
        
        if rfid:
            query = query.filter(Tag.rfid.like(f'%{rfid}%'))
        if label:
            query = query.filter(Tag.label.like(f'%{label}%'))
        if location:
            query = query.filter(Tag.last_seen.like(f'%{location}%'))
        if approval_status:
            is_approved = approval_status == 'approved'
            query = query.filter(Tag.approved == is_approved)
        if date_from:
            query = query.filter(Tag.date_seen >= date_from)
        if date_to:
            query = query.filter(Tag.date_seen <= date_to)
        
        # Execute query
        results = query.all()
        
        return render_template('advanced_search.html', results=results)
    
    return render_template('advanced_search.html', results=None)

if __name__ == '__main__':
    start_autosave()  
    
    # Start all four RFID scanners in separate threads
    rfid_thread_com3 = threading.Thread(target=run_rfid_scanner_com3)
    rfid_thread_com3.daemon = True
    rfid_thread_com3.start()
    
    rfid_thread_com4 = threading.Thread(target=run_rfid_scanner_com4)
    rfid_thread_com4.daemon = True
    rfid_thread_com4.start()

    rfid_thread_com5 = threading.Thread(target=run_rfid_scanner_com5)
    rfid_thread_com5.daemon = True
    rfid_thread_com5.start()

    rfid_thread_com6 = threading.Thread(target=run_rfid_scanner_com6)
    rfid_thread_com6.daemon = True
    rfid_thread_com6.start()
    
    app.run(debug=True, host='0.0.0.0', port=5000)
