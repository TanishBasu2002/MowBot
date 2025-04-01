from datetime import datetime
from typing import List, Dict
from sqlalchemy.orm import Session
from ..database.models import JobNote

class NoteService:
    @staticmethod
    def add_note(db: Session, job_id: int, author_id: int, author_role: str, note: str) -> JobNote:
        """Add a new note to a job"""
        new_note = JobNote(
            job_id=job_id,
            author_id=author_id,
            author_role=author_role,
            note=note,
            created_at=datetime.now()
        )
        db.add(new_note)
        db.commit()
        db.refresh(new_note)
        return new_note

    @staticmethod
    def get_notes_for_job(db: Session, job_id: int) -> List[Dict]:
        """Get all notes for a specific job"""
        notes = db.query(JobNote).filter(JobNote.job_id == job_id).order_by(JobNote.created_at.desc()).all()
        return [
            {
                "id": note.id,
                "author_id": note.author_id,
                "author_role": note.author_role,
                "note": note.note,
                "created_at": note.created_at.strftime("%Y-%m-%d %H:%M")
            } for note in notes
        ]