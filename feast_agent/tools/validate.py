"""Tools for validating correctness — schema, freshness, offline/online parity."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool

from feast import FeatureStore


def get_validate_tools(store: FeatureStore) -> list:
    """Return all validation tools bound to *store*."""

    @tool
    def validate_feature_view_schema(feature_view_name: str) -> Dict[str, Any]:
        """Validate that a feature view's schema is internally consistent:
        entities exist, fields have valid types, and the source is registered.

        Args:
            feature_view_name: Name of the feature view to validate.
        """
        issues: List[str] = []

        try:
            fv = store.get_feature_view(feature_view_name)
        except Exception as e:
            return {"valid": False, "issues": [f"Feature view not found: {e}"]}

        if hasattr(fv, "entities"):
            for ent_name in fv.entities:
                if ent_name == "__dummy":
                    continue
                try:
                    store.get_entity(ent_name)
                except Exception:
                    issues.append(f"Entity '{ent_name}' referenced but not registered.")

        if hasattr(fv, "source") and fv.source:
            try:
                store.get_data_source(fv.source.name)
            except Exception:
                issues.append(f"Data source '{fv.source.name}' referenced but not registered.")

        if hasattr(fv, "schema"):
            if not fv.schema:
                issues.append("Feature view has an empty schema (no fields defined).")

        return {
            "feature_view": feature_view_name,
            "valid": len(issues) == 0,
            "issues": issues if issues else ["Schema is valid."],
            "field_count": len(fv.schema) if hasattr(fv, "schema") else 0,
            "entity_count": len(fv.entities) if hasattr(fv, "entities") else 0,
        }

    @tool
    def validate_data_freshness(feature_view_name: str) -> Dict[str, Any]:
        """Check whether a feature view's online data is fresh based on its TTL
        and last materialization time.

        Args:
            feature_view_name: Name of the feature view to check.
        """
        try:
            fv = store.get_feature_view(feature_view_name)
        except Exception as e:
            return {"error": f"Feature view not found: {e}"}

        intervals = fv.materialization_intervals if hasattr(fv, "materialization_intervals") else []
        now = datetime.now(tz=timezone.utc)

        if not intervals:
            return {
                "feature_view": feature_view_name,
                "fresh": False,
                "reason": "Never materialized.",
                "ttl": str(fv.ttl) if fv.ttl else "None",
            }

        last_end = max(iv[1] for iv in intervals)
        age = now - last_end

        if fv.ttl and age > fv.ttl:
            return {
                "feature_view": feature_view_name,
                "fresh": False,
                "reason": f"Data is {age} old, exceeds TTL of {fv.ttl}.",
                "last_materialized": str(last_end),
                "ttl": str(fv.ttl),
            }

        return {
            "feature_view": feature_view_name,
            "fresh": True,
            "last_materialized": str(last_end),
            "age": str(age),
            "ttl": str(fv.ttl) if fv.ttl else "None",
        }

    @tool
    def dry_run_plan() -> str:
        """Run FeatureStore.plan() and return the registry and infra diff
        without applying any changes. Useful for previewing what 'apply' would do."""
        from feast.repo_contents import RepoContents

        repo_contents = RepoContents(
            projects=[],
            data_sources=list(store.list_data_sources()),
            feature_views=list(store.list_feature_views()),
            on_demand_feature_views=list(store.list_on_demand_feature_views()),
            stream_feature_views=list(store.list_stream_feature_views()),
            entities=list(store.list_entities()),
            feature_services=list(store.list_feature_services()),
            permissions=[],
        )

        try:
            registry_diff, infra_diff, _ = store.plan(repo_contents)
            parts = []
            reg_str = registry_diff.to_string()
            if reg_str.strip():
                parts.append(f"Registry changes:\n{reg_str}")
            else:
                parts.append("Registry: No changes.")

            inf_str = infra_diff.to_string()
            if inf_str.strip():
                parts.append(f"Infrastructure changes:\n{inf_str}")
            else:
                parts.append("Infrastructure: No changes.")

            return "\n\n".join(parts)
        except Exception as e:
            return f"Plan failed: {e}"

    @tool
    def check_feature_consistency(
        feature_view_name: str,
        features: Any = None,
        entity_rows: Any = None,
    ) -> Dict[str, Any]:
        """Compare offline vs online feature values to verify consistency.

        Args:
            feature_view_name: Name of the feature view, e.g. "driver_hourly_stats".
            features: Feature refs like ["driver_hourly_stats:conv_rate"].
                If omitted, all features from the view are used.
            entity_rows: List of entity dicts, e.g. [{"driver_id": 1001}].
                If omitted, a default sample row is generated.
        """
        import json as _json
        import pandas as pd

        if isinstance(entity_rows, str):
            try:
                entity_rows = _json.loads(entity_rows)
            except _json.JSONDecodeError:
                import ast
                try:
                    entity_rows = ast.literal_eval(entity_rows)
                except Exception:
                    return {"error": f"Could not parse entity_rows string: {entity_rows!r}"}

        try:
            fv = store.get_feature_view(feature_view_name)
        except Exception:
            return {"error": f"Feature view '{feature_view_name}' not found."}

        if not features:
            features = [
                f"{feature_view_name}:{f.name}"
                for f in fv.schema
                if f.name not in {e for e in fv.entities}
            ]
        elif isinstance(features, list):
            features = [
                f"{feature_view_name}:{f}" if ":" not in f else f
                for f in features
            ]

        if not entity_rows:
            entity_keys = [e for e in fv.entities if e != "__dummy"]
            if entity_keys:
                entity_rows = [{k: 1 for k in entity_keys}]
            else:
                return {"error": "Cannot determine entity keys; provide entity_rows explicitly."}
        if not isinstance(entity_rows, list):
            entity_rows = [entity_rows]

        try:
            online_resp = store.get_online_features(
                features=features,
                entity_rows=entity_rows,
            )
            online_dict = online_resp.to_dict()
        except Exception as e:
            return {"error": f"Online retrieval failed: {e}"}

        try:
            entity_df = pd.DataFrame(entity_rows)
            entity_df["event_timestamp"] = pd.Timestamp.now(tz="UTC")
            job = store.get_historical_features(entity_df=entity_df, features=features)
            offline_df = job.to_df()
        except Exception as e:
            return {"error": f"Offline retrieval failed: {e}"}

        mismatches = []
        for feat in features:
            col = feat.split(":")[-1] if ":" in feat else feat
            if col in online_dict and col in offline_df.columns:
                for i, row in enumerate(entity_rows):
                    online_val = online_dict[col][i] if i < len(online_dict[col]) else None
                    offline_val = offline_df[col].iloc[i] if i < len(offline_df) else None
                    if online_val != offline_val:
                        mismatches.append({
                            "entity": row,
                            "feature": col,
                            "online": str(online_val),
                            "offline": str(offline_val),
                        })

        return {
            "feature_view": feature_view_name,
            "consistent": len(mismatches) == 0,
            "total_checks": len(features) * len(entity_rows),
            "mismatches": mismatches[:20],
        }

    return [
        validate_feature_view_schema,
        validate_data_freshness,
        dry_run_plan,
        check_feature_consistency,
    ]
