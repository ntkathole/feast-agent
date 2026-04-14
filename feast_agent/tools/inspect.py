"""Tools for inspecting existing Feast objects — list, describe, sample."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from langchain_core.tools import tool

from feast import FeatureStore


def _extract_name(kwargs: dict) -> str:
    """Pull a name string from whatever the LLM passed.

    Accepts ``name``, ``feature_view_name``, ``feature_view_names``,
    ``entity_name``, ``data_source_name``, etc.  If the value is a list,
    takes the first element.
    """
    for key in ("name", "feature_view_name", "feature_view_names",
                "entity_name", "data_source_name", "source_name"):
        val = kwargs.get(key)
        if val is not None:
            if isinstance(val, list):
                return str(val[0]) if val else ""
            return str(val)
    return ""


def get_inspect_tools(store: FeatureStore) -> list:
    """Return all inspection tools bound to *store*."""

    @tool
    def list_all_objects() -> Dict[str, Any]:
        """List every registered Feast object: data sources, entities,
        feature views (with individual features), and feature services."""
        data_sources = store.list_data_sources()
        entities = store.list_entities()
        feature_views = store.list_feature_views()
        on_demand_fvs = store.list_on_demand_feature_views()
        stream_fvs = store.list_stream_feature_views()
        feature_services = store.list_feature_services()

        def _fv_info(fv) -> Dict[str, Any]:
            features = []
            if hasattr(fv, "schema"):
                features = [{"name": f.name, "dtype": str(f.dtype)} for f in fv.schema]
            info: Dict[str, Any] = {"name": fv.name, "type": type(fv).__name__, "features": features}
            sfvp = getattr(fv, "source_feature_view_projections", None)
            if sfvp:
                info["sources"] = list(sfvp.keys()) if isinstance(sfvp, dict) else [p.name for p in sfvp]
            if hasattr(fv, "udf_string") and fv.udf_string:
                info["transformation"] = fv.udf_string.strip()
            if hasattr(fv, "mode"):
                info["mode"] = str(fv.mode)
            return info

        def _fs_info(fs) -> Dict[str, Any]:
            projections = []
            if hasattr(fs, "feature_view_projections"):
                for proj in fs.feature_view_projections:
                    feat_names = [f.name for f in proj.features] if hasattr(proj, "features") else []
                    projections.append({
                        "feature_view": proj.name,
                        "features": feat_names,
                    })
            return {"name": fs.name, "feature_views": projections}

        all_fvs = (
            [_fv_info(fv) for fv in feature_views]
            + [_fv_info(fv) for fv in on_demand_fvs]
            + [_fv_info(fv) for fv in stream_fvs]
        )

        def _store_config_info(cfg) -> Dict[str, str]:
            """Extract online/offline store type and key settings."""
            info: Dict[str, str] = {}
            online = getattr(cfg, "online_config", None)
            if online is not None:
                info["online_store_type"] = getattr(online, "type", "sqlite")
                if hasattr(online, "path"):
                    info["online_store_path"] = str(online.path)
            else:
                info["online_store_type"] = "sqlite (default)"

            offline = getattr(cfg, "offline_config", None)
            if offline is not None:
                info["offline_store_type"] = getattr(offline, "type", "file")
            else:
                info["offline_store_type"] = "file (default)"
            return info

        store_info = _store_config_info(store.config)

        return {
            "project": store.config.project,
            "provider": store.config.provider,
            **store_info,
            "data_sources": [ds.name for ds in data_sources],
            "entities": [e.name for e in entities],
            "feature_views": all_fvs,
            "feature_services": [_fs_info(fs) for fs in feature_services],
        }

    @tool
    def describe_feature_view(name: str = "", **kwargs: Any) -> Dict[str, Any]:
        """Describe a feature view: schema, source, entities, TTL, tags,
        and transformation code. Works for all view types.

        Args:
            name: Name of the feature view to describe.
        """
        name = name or _extract_name(kwargs)
        if not name:
            return {"error": "Please provide the feature view name."}
        try:
            fv = store.get_feature_view(name)
        except Exception:
            try:
                fv = store.get_on_demand_feature_view(name)
            except Exception:
                try:
                    fv = store.get_stream_feature_view(name)
                except Exception:
                    return {"error": f"Feature view '{name}' not found in any category."}

        info: Dict[str, Any] = {
            "name": fv.name,
            "type": type(fv).__name__,
            "description": getattr(fv, "description", ""),
            "tags": dict(getattr(fv, "tags", {})),
            "owner": getattr(fv, "owner", ""),
        }

        if hasattr(fv, "entities"):
            info["entities"] = list(fv.entities)
        if hasattr(fv, "schema"):
            info["schema"] = [
                {"name": f.name, "dtype": str(f.dtype)} for f in fv.schema
            ]
        if hasattr(fv, "ttl"):
            info["ttl"] = str(fv.ttl) if fv.ttl else None
        if hasattr(fv, "online"):
            info["online"] = fv.online
        if hasattr(fv, "source") and fv.source:
            info["source"] = fv.source.name
        if hasattr(fv, "stream_source") and fv.stream_source:
            info["stream_source"] = fv.stream_source.name
        sfvp = getattr(fv, "source_feature_view_projections", None)
        if sfvp:
            info["input_feature_views"] = list(sfvp.keys()) if isinstance(sfvp, dict) else [p.name for p in sfvp]
        if hasattr(fv, "udf_string") and fv.udf_string:
            info["transformation_code"] = fv.udf_string.strip()
        if hasattr(fv, "mode"):
            info["mode"] = str(fv.mode)

        return info

    @tool
    def describe_data_source(name: str = "", **kwargs: Any) -> Dict[str, Any]:
        """Describe a data source: type, path/table, timestamp field, mappings.

        Args:
            name: Name of the data source to describe.
        """
        name = name or _extract_name(kwargs)
        if not name:
            return {"error": "Please provide the data source name."}
        try:
            ds = store.get_data_source(name)
        except Exception:
            return {"error": f"Data source '{name}' not found."}

        info: Dict[str, Any] = {
            "name": ds.name,
            "type": type(ds).__name__,
            "timestamp_field": getattr(ds, "timestamp_field", ""),
            "description": getattr(ds, "description", ""),
            "tags": dict(getattr(ds, "tags", {})),
        }
        if hasattr(ds, "path"):
            info["path"] = ds.path
        if hasattr(ds, "table"):
            info["table"] = ds.table
        if hasattr(ds, "field_mapping"):
            info["field_mapping"] = dict(ds.field_mapping) if ds.field_mapping else {}
        return info

    @tool
    def describe_entity(name: str = "", **kwargs: Any) -> Dict[str, Any]:
        """Describe an entity: join key, value type, description, and tags.

        Args:
            name: Name of the entity to describe.
        """
        name = name or _extract_name(kwargs)
        if not name:
            return {"error": "Please provide the entity name."}
        try:
            entity = store.get_entity(name)
        except Exception:
            return {"error": f"Entity '{name}' not found."}

        return {
            "name": entity.name,
            "join_key": entity.join_key,
            "value_type": str(entity.value_type),
            "description": entity.description,
            "tags": dict(getattr(entity, "tags", {})),
        }

    @tool
    def get_historical_features_sample(
        features: List[str],
        entity_dict: Dict[str, List[Any]],
    ) -> str:
        """Retrieve a sample of historical (offline) features for validation.

        Args:
            features: Feature references like ["feature_view:feature_name"].
            entity_dict: Entity columns as {column_name: [values]}, plus
                an "event_timestamp" key with datetime strings.
        """
        import pandas as pd

        entity_df = pd.DataFrame(entity_dict)
        if "event_timestamp" in entity_df.columns:
            entity_df["event_timestamp"] = pd.to_datetime(entity_df["event_timestamp"])

        try:
            job = store.get_historical_features(entity_df=entity_df, features=features)
            df = job.to_df()
            return df.head(20).to_string(index=False)
        except Exception as e:
            return f"Error retrieving historical features: {e}"

    @tool
    def get_online_features_sample(
        features: List[str],
        entity_rows: List[Dict[str, Any]],
    ) -> str:
        """Retrieve online features for the given entity rows.

        Args:
            features: Feature references like ["feature_view:feature_name"].
            entity_rows: List of dicts, each with entity key-value pairs.
        """
        try:
            resp = store.get_online_features(features=features, entity_rows=entity_rows)
            return str(resp.to_dict())
        except Exception as e:
            return f"Error retrieving online features: {e}"

    return [
        list_all_objects,
        describe_feature_view,
        describe_data_source,
        describe_entity,
        get_historical_features_sample,
        get_online_features_sample,
    ]
