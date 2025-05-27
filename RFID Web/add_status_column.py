from app import app, db, Tag, InventoryTag
from sqlalchemy import text

def add_status_column():
    with app.app_context():
        # First try to add the column using raw SQL
        try:
            with db.engine.connect() as conn:
                # Add status column to tag table
                conn.execute(text('ALTER TABLE tag ADD COLUMN status VARCHAR(10) DEFAULT "out" NOT NULL'))
                # Add status column to inventory_tag table
                conn.execute(text('ALTER TABLE inventory_tag ADD COLUMN status VARCHAR(10) DEFAULT "out" NOT NULL'))
                conn.commit()
                print("Status columns added successfully!")
        except Exception as e:
            print(f"Error adding columns: {e}")
            print("Attempting to recreate tables...")
            
            # If adding column fails, try to recreate the tables
            try:
                # Drop and recreate tables
                db.drop_all()
                db.create_all()
                print("Tables recreated successfully!")
            except Exception as e:
                print(f"Error recreating tables: {e}")
                return

if __name__ == '__main__':
    add_status_column() 