import sqlite3
from datetime import datetime

# Paths to your databases
BACKUP_DB = 'bot_data_backup.db'
CURRENT_DB = 'bot_data.db'

def migrate_data():
    # Connect to both databases
    conn_backup = sqlite3.connect(BACKUP_DB)
    conn_current = sqlite3.connect(CURRENT_DB)
    
    # Enable WAL mode for better concurrency
    conn_current.execute("PRAGMA journal_mode=WAL")
    
    # Create cursors
    cursor_backup = conn_backup.cursor()
    cursor_current = conn_current.cursor()
    
    try:
        # Disable foreign keys temporarily
        cursor_current.execute("PRAGMA foreign_keys=OFF")
        
        # Get all tables from backup
        cursor_backup.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor_backup.fetchall() if not row[0].startswith('sqlite_')]
        
        for table in tables:
            print(f"\nMigrating {table}...")
            
            # Get column info
            cursor_backup.execute(f"PRAGMA table_info({table})")
            backup_columns = [col[1] for col in cursor_backup.fetchall()]
            
            cursor_current.execute(f"PRAGMA table_info({table})")
            current_columns = [col[1] for col in cursor_current.fetchall()]
            
            # Find common columns
            common_columns = list(set(backup_columns) & set(current_columns))
            
            # Skip if no common columns
            if not common_columns:
                print(f"Skipping {table} - no matching columns")
                continue
                
            # Handle primary key conflicts
            if 'id' in common_columns:
                # Get max ID from current table
                cursor_current.execute(f"SELECT COALESCE(MAX(id), 0) FROM {table}")
                max_id = cursor_current.fetchone()[0]
                
                # Offset backup IDs
                cursor_backup.execute(f"""
                    SELECT {', '.join(common_columns)} 
                    FROM {table}
                    ORDER BY id
                """)
                
                for row in cursor_backup.fetchall():
                    row = list(row)
                    if 'id' in common_columns:
                        idx = common_columns.index('id')
                        row[idx] += max_id
                    
                    try:
                        placeholders = ', '.join(['?'] * len(common_columns))
                        cursor_current.execute(
                            f"INSERT INTO {table} ({', '.join(common_columns)}) VALUES ({placeholders})",
                            row
                        )
                    except sqlite3.IntegrityError as e:
                        if "UNIQUE" in str(e):
                            print(f"Skipping duplicate row (ID: {row[0]})")
                            continue
                        raise
            else:
                # No ID column - simple insert
                cursor_backup.execute(f"SELECT {', '.join(common_columns)} FROM {table}")
                cursor_current.executemany(
                    f"INSERT INTO {table} ({', '.join(common_columns)}) VALUES ({', '.join(['?']*len(common_columns))})",
                    cursor_backup.fetchall()
                )
            
            print(f"Migrated {cursor_current.rowcount} rows to {table}")
        
        conn_current.commit()
        print("\n✅ Migration completed successfully")
        
    except Exception as e:
        print(f"\n❌ Error during migration: {e}")
        conn_current.rollback()
    finally:
        # Re-enable foreign keys
        cursor_current.execute("PRAGMA foreign_keys=ON")
        conn_backup.close()
        conn_current.close()
        print("Database connections closed")

if __name__ == "__main__":
    print(f"Starting migration at {datetime.now()}")
    migrate_data()
    print(f"Migration completed at {datetime.now()}")