"""
ingestion_jobs 테이블 접근: enqueue, poll, status 업데이트.
"""

from sqlmodel import select
from sqlmodel import Session

from app.db.models import IngestionJob


class IngestionJobRepo:
    def create(
        self,
        session: Session,
        *,
        course_id: str,
        lecture_id: str,
        user_id: str,
        job_type: str,
        payload: dict,
    ) -> IngestionJob:
        job = IngestionJob(
            course_id=course_id,
            lecture_id=lecture_id,
            user_id=user_id,
            job_type=job_type,
            payload=payload,
            status="pending",
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        return job

    def get_next_pending(self, session: Session) -> IngestionJob | None:
        stmt = (
            select(IngestionJob)
            .where(IngestionJob.status == "pending")
            .order_by(IngestionJob.id.asc())
            .limit(1)
        )
        return session.exec(stmt).first()

    def mark_processing(self, session: Session, job_id: int) -> None:
        job = session.get(IngestionJob, job_id)
        if job:
            job.status = "processing"
            session.add(job)
            session.commit()

    def mark_done(self, session: Session, job_id: int) -> None:
        job = session.get(IngestionJob, job_id)
        if job:
            job.status = "done"
            session.add(job)
            session.commit()

    def mark_failed(self, session: Session, job_id: int, error_message: str) -> None:
        job = session.get(IngestionJob, job_id)
        if job:
            job.status = "failed"
            job.error_message = error_message
            session.add(job)
            session.commit()

    def get_by_id(self, session: Session, job_id: int) -> IngestionJob | None:
        return session.get(IngestionJob, job_id)


ingestion_job_repo = IngestionJobRepo()
