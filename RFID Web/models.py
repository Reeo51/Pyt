from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Tag(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rfid = db.Column(db.String(80), unique=True, nullable=False)
    label = db.Column(db.String(120), nullable=True)
    last_seen = db.Column(db.String(120), nullable=True)
    time_seen = db.Column(db.String(120), nullable=True)
