# file: /src/bot/utils/note_service.py
from asyncio.log import logger
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
from ..database.models import JobNote
from typing import Optional
class NoteService:
    @staticmethod
    def add_note(
        db,
        job_id: int,
        user_id: int,
        user_name: str,
        user_role: str,
        note: str,
        photo_path: Optional[str] = None
    ) -> bool:
        """Safely add a note with comprehensive error handling"""
        try:
            new_note = JobNote(
                job_id=job_id,
                author_id=user_id,
                author_name=user_name,
                author_role=user_role,
                note=note,
                photo_path=photo_path,
                created_at=datetime.now()
            )
            db.add(new_note)
            db.commit()
            return True
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Database error adding note: {e}")
            return False
        except Exception as e:
            db.rollback()
            logger.error(f"Unexpected error adding note: {e}")
            return False

    @staticmethod
    def get_notes_for_job(db, job_id: int):
        """Safely get notes for a job"""
        try:
            return db.query(JobNote).filter(
                JobNote.job_id == job_id
            ).order_by(
                JobNote.created_at.desc()
            ).all()
        except SQLAlchemyError as e:
            logger.error(f"Database error fetching notes: {e}")
            return []