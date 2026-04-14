"""Tools for analyzing and optimizing feature pipelines."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from langchain_core.tools import tool

from feast import FeatureStore


def get_optimize_tools(store: FeatureStore) -> list:
    """Return all optimization-analysis tools bound to *store*."""

    @tool
    def analyze_ttl_settings() -> Dict[str, Any]:
        """Analyze TTL settings across all feature views and flag potential issues:
        - Views with no TTL (unlimited staleness)
        - Views with very short TTLs that may cause excessive materialization
        - Views with very long TTLs that may serve stale data
        """
        feature_views = store.list_feature_views()
        analysis = []
        recommendations = []

        for fv in feature_views:
            ttl = fv.ttl
            entry: Dict[str, Any] = {
                "name": fv.name,
                "ttl": str(ttl) if ttl else "None (unlimited)",
                "online": getattr(fv, "online", True),
            }

            if ttl is None or ttl == timedelta(0):
                entry["issue"] = "No TTL set — online data never expires, risk of serving stale features."
                recommendations.append(
                    f"'{fv.name}': Consider setting a TTL (e.g., 1 day) to prevent stale data."
                )
            elif ttl < timedelta(hours=1):
                entry["issue"] = "Very short TTL — requires frequent materialization."
                recommendations.append(
                    f"'{fv.name}': TTL is {ttl}. Ensure materialization runs frequently enough."
                )
            elif ttl > timedelta(days=30):
                entry["issue"] = "Very long TTL — data could be up to 30+ days stale."
                recommendations.append(
                    f"'{fv.name}': TTL is {ttl}. Consider shortening if freshness matters."
                )
            else:
                entry["issue"] = None

            analysis.append(entry)

        return {
            "feature_views_analyzed": len(analysis),
            "details": analysis,
            "recommendations": recommendations if recommendations else ["All TTLs look reasonable."],
        }

    @tool
    def analyze_feature_freshness() -> Dict[str, Any]:
        """Analyze materialization freshness for all feature views. Reports how
        long ago each view was last materialized and whether it exceeds its TTL."""
        feature_views = store.list_feature_views()
        now = datetime.now(tz=timezone.utc)
        analysis = []

        for fv in feature_views:
            intervals = fv.materialization_intervals if hasattr(fv, "materialization_intervals") else []

            if not intervals:
                analysis.append({
                    "name": fv.name,
                    "status": "never_materialized",
                    "last_materialized": None,
                    "age": None,
                    "ttl": str(fv.ttl) if fv.ttl else "None",
                    "stale": True,
                })
                continue

            last_end = max(iv[1] for iv in intervals)
            age = now - last_end
            stale = bool(fv.ttl and age > fv.ttl)

            analysis.append({
                "name": fv.name,
                "status": "stale" if stale else "fresh",
                "last_materialized": str(last_end),
                "age": str(age),
                "ttl": str(fv.ttl) if fv.ttl else "None",
                "stale": stale,
            })

        stale_count = sum(1 for a in analysis if a["stale"])
        return {
            "total_views": len(analysis),
            "stale_count": stale_count,
            "fresh_count": len(analysis) - stale_count,
            "details": analysis,
        }

    @tool
    def suggest_optimizations() -> Dict[str, Any]:
        """Perform a holistic review of the feature store and suggest
        optimizations: unused features, redundant sources, TTL mismatches,
        and materialization gaps."""
        data_sources = store.list_data_sources()
        feature_views = store.list_feature_views()
        on_demand_fvs = store.list_on_demand_feature_views()
        feature_services = store.list_feature_services()

        suggestions: List[str] = []

        # Check for data sources not used by any feature view
        used_sources = set()
        for fv in feature_views:
            if hasattr(fv, "source") and fv.source:
                used_sources.add(fv.source.name)
            if hasattr(fv, "stream_source") and fv.stream_source:
                used_sources.add(fv.stream_source.name)
        for odfv in on_demand_fvs:
            if hasattr(odfv, "sources"):
                for src in odfv.sources:
                    if hasattr(src, "name"):
                        used_sources.add(src.name)

        unused_sources = [ds.name for ds in data_sources if ds.name not in used_sources]
        if unused_sources:
            suggestions.append(
                f"Unused data sources (not referenced by any feature view): {unused_sources}. "
                "Consider removing them to reduce clutter."
            )

        # Check for feature views not included in any feature service
        served_fvs = set()
        for fs in feature_services:
            if hasattr(fs, "feature_view_projections"):
                for proj in fs.feature_view_projections:
                    served_fvs.add(proj.name)
        unserved = [fv.name for fv in feature_views if fv.name not in served_fvs]
        if unserved and feature_services:
            suggestions.append(
                f"Feature views not in any FeatureService: {unserved}. "
                "If they're meant for serving, add them to a FeatureService."
            )

        # Check for very large schemas
        for fv in feature_views:
            if hasattr(fv, "schema") and len(fv.schema) > 50:
                suggestions.append(
                    f"'{fv.name}' has {len(fv.schema)} fields. Consider splitting "
                    "into multiple focused feature views for better maintainability."
                )

        # Check for feature views with online=False that are in feature services
        for fv in feature_views:
            if not getattr(fv, "online", True) and fv.name in served_fvs:
                suggestions.append(
                    f"'{fv.name}' has online=False but is in a FeatureService. "
                    "Online serving will not work for this view."
                )

        if not suggestions:
            suggestions.append("No issues found — the feature store looks well-configured.")

        return {
            "total_data_sources": len(data_sources),
            "total_feature_views": len(feature_views),
            "total_on_demand_fvs": len(on_demand_fvs),
            "total_feature_services": len(feature_services),
            "suggestions": suggestions,
        }

    return [
        analyze_ttl_settings,
        analyze_feature_freshness,
        suggest_optimizations,
    ]
