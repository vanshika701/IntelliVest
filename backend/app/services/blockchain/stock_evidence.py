"""Stock-prediction evidence from the real Phase 4 model (B10, B18).

Reads the predictions Phase 4 already stored; it never runs or imports the
model, so changes to the predictor don't reach here. It relies on these
fields of a stored prediction only: ticker, as_of, horizon_days, chance_beat,
target, model_version, artifact_hash (optional: low, mid, high).

Since Phase 4 model 2.0.0 the score is the chance the stock beats the Nifty
50 over the horizon (`target` = excess_log_return_vs_nifty), and low, mid
and high are excess log returns. Rows from older models (chance_up, plain
returns) give NO_DATA.
"""

import math
from datetime import UTC, datetime

from app.services.blockchain import hashing
from app.services.blockchain.formats import (
    BPS,
    MAX_EVIDENCE_AGE_SECONDS,
    Evidence,
    EvidenceResult,
    EvidenceStatus,
    Step,
)

MODEL_NAME = "intellivest/stock-predictor"
TARGET = "excess_log_return_vs_nifty"
_OPTIONAL_OUTPUTS = ("low", "mid", "high")  # excess log returns vs the Nifty 50


def model_ref(record: dict) -> tuple[bytes, bytes, bytes]:
    """(modelId, version, artifactHash) for registering this model version."""
    return (
        hashing.model_id(MODEL_NAME),
        hashing.model_id(record["model_version"]),
        bytes.fromhex(record["artifact_hash"]),
    )


def build_stock_evidence(
    task_id: bytes,
    ticker: str,
    horizon_days: int,
    records: list[dict],
    now: datetime,
    registered_version: str,
) -> EvidenceResult:
    """`records` is every stored horizon of the ticker's newest day;
    `registered_version` is the model version the stock key is registered for.

    Missing, week-old or unregistered-model predictions give NO_DATA, so the
    mandate decides (ask the owner or reject). The contract only accepts
    evidence under a registered version, so a retrained model must be
    registered, and accepted by each owner, before its predictions count.
    """

    def no_data(why: str) -> EvidenceResult:
        return _no_data(task_id, ticker, horizon_days, now, registered_version, why)

    record = _nearest(records, horizon_days)
    if record is None:
        return no_data("no stored prediction")
    if record["model_version"] != registered_version:
        return no_data(f"prediction made by unregistered model version {record['model_version']}")
    as_of = _timestamp(record["as_of"])
    if now.timestamp() - as_of > MAX_EVIDENCE_AGE_SECONDS:
        return no_data("prediction older than 7 days")

    inputs = {
        "ticker": ticker,
        "as_of": datetime.fromtimestamp(as_of, UTC).date().isoformat(),
        "horizon_days": int(record["horizon_days"]),
        "model_version": record["model_version"],
        "artifact_hash": record["artifact_hash"],
        "target": record["target"],
    }
    score = _bps(record["chance_beat"], 0, BPS)
    outputs = {"chance_beat_bps": score}
    outputs |= {f"{k}_bps": _bps(record[k]) for k in _OPTIONAL_OUTPUTS if _is_number(record.get(k))}
    model, version, _ = model_ref(record)
    evidence = Evidence(
        taskId=task_id,
        step=int(Step.STOCK_PREDICTION),
        status=int(EvidenceStatus.OK),
        modelId=model,
        modelVersion=version,
        inputHash=hashing.hash_data(inputs),
        outputHash=hashing.hash_data(outputs),
        score=score,
        count=0,
        horizonDays=int(record["horizon_days"]),
        asOf=as_of,
    )
    return EvidenceResult(evidence, inputs, outputs)


async def stock_evidence(
    task_id: bytes,
    ticker: str,
    horizon_days: int,
    registered_version: str,
    now: datetime | None = None,
) -> EvidenceResult:
    from app.data import prediction_repository

    records = await prediction_repository.get_latest_for_ticker(ticker)
    return build_stock_evidence(
        task_id, ticker, horizon_days, records, now or datetime.now(UTC), registered_version
    )


def _nearest(records: list[dict], horizon_days: int) -> dict | None:
    usable = [
        r
        for r in records
        if r.get("horizon_days", 0) > 0
        and r.get("target") == TARGET
        and _is_number(r.get("chance_beat"))
    ]
    if not usable:
        return None
    target = math.log(max(horizon_days, 1))
    return min(usable, key=lambda r: abs(math.log(r["horizon_days"]) - target))


def _no_data(
    task_id: bytes, ticker: str, horizon_days: int, now: datetime, version: str, why: str
) -> EvidenceResult:
    inputs = {"ticker": ticker, "horizon_days": horizon_days, "reason": why}
    outputs: dict = {}
    model = hashing.model_id(MODEL_NAME)
    evidence = Evidence(
        taskId=task_id,
        step=int(Step.STOCK_PREDICTION),
        status=int(EvidenceStatus.NO_DATA),
        modelId=model,
        modelVersion=hashing.model_id(version),
        inputHash=hashing.hash_data(inputs),
        outputHash=hashing.hash_data(outputs),
        score=0,
        count=0,
        horizonDays=horizon_days,
        asOf=int(now.timestamp()),
    )
    return EvidenceResult(evidence, inputs, outputs)


def _timestamp(value: datetime) -> int:
    if value.tzinfo is None:  # MongoDB returns naive UTC
        value = value.replace(tzinfo=UTC)
    return int(value.timestamp())


def _bps(value: float, low: int = -(2**31), high: int = 2**31 - 1) -> int:
    return max(low, min(high, round(value * BPS)))


def _is_number(value) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)
