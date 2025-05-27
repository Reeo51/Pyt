from app import app, db
import os

def reset_database():
    with app.app_context():
        # Get the database file path
        db_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
        
        # Remove the database file if it exists
        if os.path.exists(db_path):
            try:
                # Close all connections
                db.session.remove()
                db.engine.dispose()
                
                # Delete the file
                os.remove(db_path)
                print(f"Deleted existing database: {db_path}")
            except Exception as e:
                print(f"Error deleting database: {e}")
                return
        
        # Create new database with all tables
        try:
            db.create_all()
            print("Created new database with all tables!")
        except Exception as e:
            print(f"Error creating database: {e}")
            return

if __name__ == '__main__':
    reset_database() 