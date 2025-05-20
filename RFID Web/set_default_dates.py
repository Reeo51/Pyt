from app import app, db, Tag, InventoryTag
from datetime import datetime

with app.app_context():
    # Set current date for all existing records that don't have a date_seen
    current_date = datetime.now().strftime("%Y-%m-%d")
    
    # Update Tag records
    tags = Tag.query.all()
    updated_count = 0
    for tag in tags:
        if tag.date_seen is None:
            tag.date_seen = current_date
            updated_count += 1
    
    # Update InventoryTag records
    inventory_tags = InventoryTag.query.all()
    inventory_updated_count = 0
    for tag in inventory_tags:
        if tag.date_seen is None:
            tag.date_seen = current_date
            inventory_updated_count += 1
    
    # Commit all changes
    db.session.commit()
    
    print(f"Updated {updated_count} Tag records and {inventory_updated_count} InventoryTag records with default date.") 