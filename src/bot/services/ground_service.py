from datetime import datetime
from typing import List, Optional, Tuple
from pathlib import Path
from sqlalchemy.orm import Session
from sqlalchemy import and_

from ..database.models import Ground
from ..config.settings import PHOTOS_DIR, MAX_PHOTOS_PER_JOB

class GroundService:
    """Service class for handling ground-related operations."""

    @staticmethod
    async def get_ground(db: Session, ground_id: int) -> Optional[Ground]:
        """Get a ground by ID."""
        return db.query(Ground).filter(Ground.id == ground_id).first()

    @staticmethod
    async def get_employee_grounds(db: Session, employee_id: int, date: Optional[str] = None) -> List[Ground]:
        """Get all grounds assigned to an employee."""
        query = db.query(Ground).filter(Ground.assigned_to == employee_id)
        if date:
            query = query.filter(Ground.scheduled_date == date)
        return query.all()

    @staticmethod
    async def start_job(db: Session, ground_id: int) -> Tuple[bool, str]:
        """Start a job."""
        ground = await GroundService.get_ground(db, ground_id)
        if not ground:
            return False, "Ground not found"
        
        if ground.status == 'completed':
            return False, "Job is already completed"
        
        ground.status = 'in_progress'
        ground.start_time = datetime.now()
        db.commit()
        return True, "Job started successfully"

    @staticmethod
    async def finish_job(db: Session, ground_id: int) -> Tuple[bool, str]:
        """Finish a job."""
        ground = await GroundService.get_ground(db, ground_id)
        if not ground:
            return False, "Ground not found"
        
        if ground.status == 'completed':
            return False, "Job is already completed"
        
        ground.status = 'completed'
        ground.finish_time = datetime.now()
        db.commit()
        return True, "Job completed successfully"

    @staticmethod
    async def add_photo(db: Session, ground_id: int, photo_path: str) -> Tuple[bool, str, int]:
        """Add a photo to a ground."""
        ground = await GroundService.get_ground(db, ground_id)
        if not ground:
            return False, "Ground not found", 0

        current_photos = ground.photos.split('|') if ground.photos else []
        if len(current_photos) >= MAX_PHOTOS_PER_JOB:
            return False, f"Maximum number of photos ({MAX_PHOTOS_PER_JOB}) reached", len(current_photos)

        new_photos = ground.photos.strip() + '|' + photo_path if ground.photos else photo_path
        ground.photos = new_photos
        db.commit()
        
        return True, "Photo added successfully", len(new_photos.split('|'))

    @staticmethod
    async def update_note(db: Session, ground_id: int, note: str) -> Tuple[bool, str]:
        """Update the note for a ground."""
        ground = await GroundService.get_ground(db, ground_id)
        if not ground:
            return False, "Ground not found"
        
        ground.notes = note
        db.commit()
        return True, "Note updated successfully"

    @staticmethod
    async def assign_to_employee(
        db: Session, 
        ground_id: int, 
        employee_id: int, 
        scheduled_date: str
    ) -> Tuple[bool, str]:
        """Assign a ground to an employee."""
        ground = await GroundService.get_ground(db, ground_id)
        if not ground:
            return False, "Ground not found"
        
        ground.assigned_to = employee_id
        ground.scheduled_date = scheduled_date
        ground.status = 'pending'
        db.commit()
        return True, "Ground assigned successfully"

    @staticmethod
    async def reset_completed_jobs(db: Session) -> int:
        """Reset all completed jobs."""
        result = db.query(Ground).filter(
            and_(
                Ground.status == 'completed',
                Ground.scheduled_date == datetime.now().strftime('%Y-%m-%d')
            )
        ).update({
            'status': 'pending',
            'assigned_to': None,
            'finish_time': None
        })
        db.commit()
        return result 