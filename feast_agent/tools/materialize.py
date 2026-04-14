"""Tools for materializing features — backfills and offline-to-online sync."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool

from feast import FeatureStore


def get_materialize_tools(store: FeatureStore) -> list:
    """Return all materialization tools bound to *store*."""

    @tool
    def materialize(
        start_date: str,
        end_date: str,
        feature_view_names: Optional[List[str]] = None,
    ) -> str:
        """Materialize (backfill) feature data from the offline store to the
        online store for a specific date range.

        Args:
            start_date: Start of the range as ISO-8601 string (e.g. "2026-01-01").
            end_date: End of the range as ISO-8601 string (e.g. "2026-04-13").
            feature_view_names: Optional list of specific feature view names.
                If omitted, all feature views are materialized.
        """
        start = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
        end = datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc)

        store.materialize(
            start_date=start,
            end_date=end,
            feature_views=feature_view_names,
        )

        scope = feature_view_names or "all feature views"
        return (
            f"Materialized {scope} from {start.date()} to {end.date()}."
        )

    @tool
    def materialize_incremental(
        end_date: str,
        feature_view_names: Optional[List[str]] = None,
    ) -> str:
        """Incrementally materialize features up to a given date. This picks up
        from where the last materialization left off.

        Args:
            end_date: End of the range as ISO-8601 string (e.g. "2026-04-13").
            feature_view_names: Optional list of specific feature view names.
                If omitted, all feature views are materialized.
        """
        end = datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc)

        store.materialize_incremental(
            end_date=end,
            feature_views=feature_view_names,
        )

        scope = feature_view_names or "all feature views"
        return f"Incremental materialization of {scope} completed up to {end.date()}."

    @tool
    def get_materialization_status() -> Dict[str, Any]:
        """Check the materialization status for all feature views — when they
        were last materialized, their TTL, and whether they may be stale."""
        feature_views = store.list_feature_views()
        status = []
        for fv in feature_views:
            intervals = fv.materialization_intervals if hasattr(fv, "materialization_intervals") else []
            last_end = None
            if intervals:
                last_end = max(iv[1] for iv in intervals)

            now = datetime.now(tz=timezone.utc)
            stale = False
            if last_end and fv.ttl:
                stale = (now - last_end) > fv.ttl

            status.append({
                "name": fv.name,
                "ttl": str(fv.ttl) if fv.ttl else "None",
                "last_materialized": str(last_end) if last_end else "Never",
                "intervals_count": len(intervals),
                "possibly_stale": stale,
            })

        if not status:
            return {"message": "No feature views found."}
        return {"feature_views": status}

    @tool
    def materialize_last_n_days(
        days: int,
        feature_view_names: Optional[List[str]] = None,
    ) -> str:
        """Convenience: materialize the last N days up to now.

        Args:
            days: Number of days to backfill.
            feature_view_names: Optional list of specific feature view names.
        """
        now = datetime.now(tz=timezone.utc)
        start = now - timedelta(days=days)

        store.materialize(
            start_date=start,
            end_date=now,
            feature_views=feature_view_names,
        )

        scope = feature_view_names or "all feature views"
        return f"Materialized {scope} for the last {days} day(s) ({start.date()} to {now.date()})."

    return [
        materialize,
        materialize_incremental,
        get_materialization_status,
        materialize_last_n_days,
    ]
