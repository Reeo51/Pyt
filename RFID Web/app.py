from flask import Flask, render_template, redirect, url_for, request, flash, Response, jsonify
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

class InventoryTag(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rfid = db.Column(db.String(120), unique=True, nullable=False)
    label = db.Column(db.String(120), nullable=False)
    last_seen = db.Column(db.String(120), nullable=False)
    time_seen = db.Column(db.String(120), nullable=False)
    date_seen = db.Column(db.String(120), nullable=True)
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
    location = "Communication Laboratory"  # Override location parameter
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
                        'location': 'Communication Lab'  
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
