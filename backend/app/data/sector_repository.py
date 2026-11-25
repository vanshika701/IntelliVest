"""Data-access layer for `sector_snapshots`: one precomputed document per sector."""

from pymongo import ReplaceOne

from app.data.collections import get_sector_snapshots_collection


async def replace_snapshots(snapshots: list[dict]) -> None:
    collection = get_sector_snapshots_collection()
    if snapshots:
        await collection.bulk_write([ReplaceOne({"sector": s["sector"]}, s, upsert=True) for s in snapshots])
    # Drop sectors removed from the mapping.
    await collection.delete_many({"sector": {"$nin": [s["sector"] for s in snapshots]}})


async def list_snapshots() -> list[dict]:
    return await get_sector_snapshots_collection().find({}, {"_id": 0}).sort("name", 1).to_list(length=100)


async def get_snapshot(sector: str) -> dict | None:
    return await get_sector_snapshots_collection().find_one({"sector": sector}, {"_id": 0})
