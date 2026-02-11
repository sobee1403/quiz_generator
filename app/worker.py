"""
Async Worker: ingestion_jobs 큐를 폴링해 pending 작업을 처리.
실행: python -m app.worker
"""

import logging
import sys
import time

from app.db.connection import get_session
from app.db.repositories.ingestion_job import ingestion_job_repo
from app.services.ingestion_pipeline import run_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

POLL_INTERVAL_SEC = 5


def main() -> None:
    logger.info("Ingestion worker 시작 (poll_interval=%ss)", POLL_INTERVAL_SEC)
    while True:
        try:
            with get_session() as session:
                job = ingestion_job_repo.get_next_pending(session)
            if job and job.id is not None:
                logger.info("Job 처리 시작 job_id=%s", job.id)
                run_pipeline(job.id)
            else:
                time.sleep(POLL_INTERVAL_SEC)
        except KeyboardInterrupt:
            logger.info("Worker 종료")
            break
        except Exception:
            logger.exception("Worker 루프 오류")
            time.sleep(POLL_INTERVAL_SEC)


if __name__ == "__main__":
    main()
