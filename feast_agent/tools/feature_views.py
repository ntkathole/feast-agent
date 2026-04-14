"""Tools for creating and applying feature views."""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool

from feast import FeatureStore

from feast_agent.tools.registry import _resolve_feast_type


def get_feature_view_tools(store: FeatureStore) -> list:
    """Return all feature-view creation tools bound to *store*."""

    @tool
    def create_feature_view(
        name: str,
        source_name: str,
        entity_names: List[str],
        schema_fields: List[Dict[str, str]],
        ttl_seconds: int = 86400,
        online: bool = True,
        description: str = "",
        tags: Optional[Dict[str, str]] = None,
    ) -> str:
        """Create and register a standard FeatureView.

        Args:
            name: Unique name for the feature view.
            source_name: Name of an already-registered data source.
            entity_names: List of entity names this view is keyed on.
            schema_fields: List of {"name": "col", "dtype": "Float64"} dicts
                describing the features. dtype can be String, Int32, Int64,
                Float32, Float64, Bool, Bytes, UnixTimestamp, Json, Map.
            ttl_seconds: Time-to-live in seconds (default 86400 = 1 day).
            online: Whether to make this view available in the online store.
            description: Human-readable description.
            tags: Optional metadata tags.
        """
        from feast import FeatureView, Field

        source = store.get_data_source(source_name)

        fields = []
        for f in schema_fields:
            feast_type = _resolve_feast_type(f["dtype"])
            fields.append(Field(name=f["name"], dtype=feast_type))

        fv = FeatureView(
            name=name,
            source=source,
            entities=entity_names,
            schema=fields,
            ttl=timedelta(seconds=ttl_seconds),
            online=online,
            description=description,
            tags=tags or {},
        )
        store.apply([fv])
        field_summary = ", ".join(f"{f['name']}({f['dtype']})" for f in schema_fields)
        return (
            f"Created FeatureView '{name}' with {len(fields)} features "
            f"[{field_summary}], source='{source_name}', "
            f"entities={entity_names}, ttl={ttl_seconds}s."
        )

    @tool
    def create_batch_feature_view(
        name: str,
        source_name: str,
        entity_names: List[str],
        schema_fields: List[Dict[str, str]],
        ttl_seconds: int = 86400,
        online: bool = True,
        description: str = "",
        tags: Optional[Dict[str, str]] = None,
    ) -> str:
        """Create and register a BatchFeatureView (for batch-computed features).

        Args:
            name: Unique name for the batch feature view.
            source_name: Name of an already-registered batch data source.
            entity_names: List of entity names.
            schema_fields: List of {"name": "col", "dtype": "Float64"} dicts.
            ttl_seconds: Time-to-live in seconds.
            online: Whether to enable online serving.
            description: Human-readable description.
            tags: Optional metadata tags.
        """
        from feast import BatchFeatureView, Field

        source = store.get_data_source(source_name)

        fields = []
        for f in schema_fields:
            feast_type = _resolve_feast_type(f["dtype"])
            fields.append(Field(name=f["name"], dtype=feast_type))

        bfv = BatchFeatureView(
            name=name,
            source=source,
            entities=entity_names,
            schema=fields,
            ttl=timedelta(seconds=ttl_seconds),
            online=online,
            description=description,
            tags=tags or {},
        )
        store.apply([bfv])
        return (
            f"Created BatchFeatureView '{name}' with {len(fields)} features, "
            f"source='{source_name}', entities={entity_names}."
        )

    @tool
    def create_stream_feature_view(
        name: str,
        source_name: str,
        entity_names: List[str],
        schema_fields: List[Dict[str, str]],
        ttl_seconds: int = 86400,
        online: bool = True,
        description: str = "",
        tags: Optional[Dict[str, str]] = None,
    ) -> str:
        """Create and register a StreamFeatureView (for real-time streaming sources).

        The source must be a KafkaSource or KinesisSource that has already been
        registered.

        Args:
            name: Unique name for the stream feature view.
            source_name: Name of an already-registered stream data source
                (KafkaSource or KinesisSource).
            entity_names: List of entity names.
            schema_fields: List of {"name": "col", "dtype": "Float64"} dicts.
            ttl_seconds: Time-to-live in seconds.
            online: Whether to enable online serving.
            description: Human-readable description.
            tags: Optional metadata tags.
        """
        from feast import Field, StreamFeatureView

        source = store.get_data_source(source_name)

        fields = []
        for f in schema_fields:
            feast_type = _resolve_feast_type(f["dtype"])
            fields.append(Field(name=f["name"], dtype=feast_type))

        sfv = StreamFeatureView(
            name=name,
            source=source,
            entities=entity_names,
            schema=fields,
            ttl=timedelta(seconds=ttl_seconds),
            online=online,
            description=description,
            tags=tags or {},
        )
        store.apply([sfv])
        return (
            f"Created StreamFeatureView '{name}' with {len(fields)} features, "
            f"source='{source_name}', entities={entity_names}."
        )

    @tool
    def delete_feature_view(name: str) -> str:
        """Delete a feature view by name (works for any view type).

        Args:
            name: Name of the feature view to delete.
        """
        try:
            store.delete_feature_view(name)
            return f"Deleted feature view '{name}'."
        except Exception as e:
            return f"Error deleting feature view '{name}': {e}"

    return [
        create_feature_view,
        create_batch_feature_view,
        create_stream_feature_view,
        delete_feature_view,
    ]
