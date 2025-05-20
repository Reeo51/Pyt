from app import app, db
from sqlalchemy import text

with app.app_context():
    # Add column to the database without losing data
    with db.engine.connect() as conn:
        conn.execute(text('ALTER TABLE tag ADD COLUMN date_seen TEXT'))
        conn.execute(text('ALTER TABLE inventory_tag ADD COLUMN date_seen TEXT'))
        conn.commit()
    print("Database updated successfully with date_seen column!") 