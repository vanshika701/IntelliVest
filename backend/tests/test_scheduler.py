"""Unit test — verifies the scheduler registers the expected ingestion
jobs and can be started/stopped cleanly, without waiting for any job to
actually fire (that would mean waiting up to an hour in a test)."""

from app.core.scheduler import scheduler, start_scheduler, stop_scheduler


async def test_start_scheduler_registers_all_three_ingestion_jobs() -> None:
    # AsyncIOScheduler.start() needs a running event loop (it attaches
    # itself to one), which is why this test is async even though it
    # doesn't await anything itself.
    start_scheduler()
    try:
        job_ids = {job.id for job in scheduler.get_jobs()}
        assert job_ids == {"market_data_ingestion", "news_ingestion", "reddit_ingestion"}
        assert scheduler.running
    finally:
        # Just needs to not raise — shutdown(wait=False) doesn't flip
        # scheduler.running synchronously, so there's nothing further to
        # assert here without depending on APScheduler's internal timing.
        stop_scheduler()
