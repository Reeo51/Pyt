from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import UserMixin, LoginManager, login_user, login_required, current_user, logout_user
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'mysecretkey'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///rfid.db'
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

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

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

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
    tags = Tag.query.all()

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

# Delete Route
@app.route('/delete/<int:id>', methods=['GET', 'POST'])
@login_required
def delete(id):
    tag = Tag.query.get_or_404(id)
    db.session.delete(tag)
    db.session.commit()
    flash('RFID Tag deleted successfully!', 'success')
    return redirect(url_for('dashboard'))

# Example endpoint to simulate RFID scan (to be replaced with actual RFID handler)
@app.route('/scan/<rfid>/<location>')
def scan_rfid(rfid, location):
    tag = Tag.query.filter_by(rfid=rfid).first()
    time_now = datetime.now().strftime("%H:%M:%S")
    if tag:
        tag.last_seen = location
        tag.time_seen = time_now
    else:
        tag = Tag(rfid=rfid, label="New Tag", last_seen=location, time_seen=time_now)
        db.session.add(tag)
    db.session.commit()
    return f"RFID {rfid} scanned at {location} at {time_now}"

# This line ensures the database tables are created when the app is first run
with app.app_context():
    db.create_all()

# To make the Flask app accessible on the local network, use 0.0.0.0 for host
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)