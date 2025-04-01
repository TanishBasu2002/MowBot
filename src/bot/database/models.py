# file: src/bot/database/models.py
from datetime import datetime
from typing import Optional, List
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from ..config.settings import DATABASE_PATH

Base = declarative_base()

class Ground(Base):
    __tablename__ = 'grounds_data'

    id = Column(Integer, primary_key=True)
    site_name = Column(String, unique=True, nullable=False)
    quote = Column(String)
    address = Column(String)
    order_no = Column(String)
    order_period = Column(String)
    area = Column(String)
    summer_schedule = Column(String)
    winter_schedule = Column(String)
    contact = Column(String)
    gate_code = Column(String)
    map_link = Column(String)
    assigned_to = Column(Integer)
    status = Column(String, default='pending')
    photos = Column(String)
    start_time = Column(DateTime)
    finish_time = Column(DateTime)
    notes = Column(String)
    scheduled_date = Column(String)

    def to_dict(self) -> dict:
        """Convert the model to a dictionary."""
        return {
            'id': self.id,
            'site_name': self.site_name,
            'quote': self.quote,
            'address': self.address,
            'order_no': self.order_no,
            'order_period': self.order_period,
            'area': self.area,
            'summer_schedule': self.summer_schedule,
            'winter_schedule': self.winter_schedule,
            'contact': self.contact,
            'gate_code': self.gate_code,
            'map_link': self.map_link,
            'assigned_to': self.assigned_to,
            'status': self.status,
            'photos': self.photos.split('|') if self.photos else [],
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'finish_time': self.finish_time.isoformat() if self.finish_time else None,
            'notes': self.notes,
            'scheduled_date': self.scheduled_date
        }

    @property
    def photo_count(self) -> int:
        """Get the number of photos for this ground."""
        return len(self.photos.split('|')) if self.photos else 0

    @property
    def duration(self) -> Optional[str]:
        """Calculate the duration of the job."""
        if self.start_time and self.finish_time:
            duration = self.finish_time - self.start_time
            return str(duration).split('.')[0]
        return None
class JobNote(Base):
    __tablename__ = 'job_notes'
    
    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey('grounds_data.id'))
    author_id = Column(Integer)
    author_role = Column(String)
    note = Column(String)
    created_at = Column(DateTime, default=datetime.now)
# Database initialization
engine = create_engine(f'sqlite:///{DATABASE_PATH}')
SessionLocal = sessionmaker(bind=engine)

def init_db():
    """Initialize the database."""
    Base.metadata.create_all(engine)

def get_db():
    """Get a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close() 