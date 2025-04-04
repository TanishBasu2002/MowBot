from src.bot.database import engine
from sqlalchemy import text

def upgrade():
    with engine.connect() as conn:
        conn.execute(text("""
            ALTER TABLE job_notes 
            ADD COLUMN author_name TEXT
        """))
        conn.commit()

if __name__ == "__main__":
    upgrade()