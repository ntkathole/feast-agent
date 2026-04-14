"""Tools for registering data sources, entities, and feature services."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from langchain_core.tools import tool

from feast import FeatureStore


def _resolve_feast_type(type_name: str):
    """Map a user-friendly type name to a Feast PrimitiveFeastType."""
    from feast.types import PrimitiveFeastType

    mapping = {t.name.lower(): t for t in PrimitiveFeastType}
    mapping.update({
        "string": PrimitiveFeastType.STRING,
        "int": PrimitiveFeastType.INT64,
        "int32": PrimitiveFeastType.INT32,
        "int64": PrimitiveFeastType.INT64,
        "float": PrimitiveFeastType.FLOAT32,
        "float32": PrimitiveFeastType.FLOAT32,
        "float64": PrimitiveFeastType.FLOAT64,
        "double": PrimitiveFeastType.FLOAT64,
        "bool": PrimitiveFeastType.BOOL,
        "boolean": PrimitiveFeastType.BOOL,
        "bytes": PrimitiveFeastType.BYTES,
        "timestamp": PrimitiveFeastType.UNIX_TIMESTAMP,
        "unix_timestamp": PrimitiveFeastType.UNIX_TIMESTAMP,
        "json": PrimitiveFeastType.JSON,
        "map": PrimitiveFeastType.MAP,
    })
    key = type_name.strip().lower()
    if key not in mapping:
        raise ValueError(
            f"Unknown type '{type_name}'. Supported: {sorted(set(mapping.keys()))}"
        )
    return mapping[key]


def get_registry_tools(store: FeatureStore) -> list:
    """Return all registration tools bound to *store*."""

    @tool
    def register_file_source(
        name: str,
        path: str,
        timestamp_field: str,
        created_timestamp_column: str = "",
        description: str = "",
        field_mapping: Optional[Dict[str, str]] = None,
        tags: Optional[Dict[str, str]] = None,
    ) -> str:
        """Register a file-based (Parquet/CSV) data source with Feast.

        Args:
            name: Unique name for the data source.
            path: File path to the Parquet or CSV file.
            timestamp_field: Column name containing event timestamps.
            created_timestamp_column: Optional column for created timestamps.
            description: Human-readable description.
            field_mapping: Optional dict mapping source columns to Feast names.
            tags: Optional metadata tags.
        """
        from feast import FileSource

        ds = FileSource(
            name=name,
            path=path,
            timestamp_field=timestamp_field,
            created_timestamp_column=created_timestamp_column or "",
            description=description,
            field_mapping=field_mapping or {},
            tags=tags or {},
        )
        store.apply([ds])
        return f"Registered FileSource '{name}' pointing to '{path}'."

    @tool
    def register_bigquery_source(
        name: str,
        table: str,
        timestamp_field: str,
        created_timestamp_column: str = "",
        description: str = "",
        field_mapping: Optional[Dict[str, str]] = None,
        tags: Optional[Dict[str, str]] = None,
    ) -> str:
        """Register a BigQuery table as a data source with Feast.

        Args:
            name: Unique name for the data source.
            table: Fully qualified BigQuery table (project.dataset.table).
            timestamp_field: Column name containing event timestamps.
            created_timestamp_column: Optional column for created timestamps.
            description: Human-readable description.
            field_mapping: Optional dict mapping source columns to Feast names.
            tags: Optional metadata tags.
        """
        from feast import BigQuerySource

        ds = BigQuerySource(
            name=name,
            table=table,
            timestamp_field=timestamp_field,
            created_timestamp_column=created_timestamp_column or "",
            description=description,
            field_mapping=field_mapping or {},
            tags=tags or {},
        )
        store.apply([ds])
        return f"Registered BigQuerySource '{name}' for table '{table}'."

    @tool
    def register_push_source(
        name: str,
        batch_source_name: str,
        description: str = "",
        tags: Optional[Dict[str, str]] = None,
    ) -> str:
        """Register a push source backed by an existing batch source.

        Args:
            name: Unique name for the push source.
            batch_source_name: Name of an already-registered batch data source.
            description: Human-readable description.
            tags: Optional metadata tags.
        """
        from feast import PushSource

        batch_source = store.get_data_source(batch_source_name)
        ds = PushSource(
            name=name,
            batch_source=batch_source,
            description=description,
            tags=tags or {},
        )
        store.apply([ds])
        return f"Registered PushSource '{name}' backed by '{batch_source_name}'."

    @tool
    def register_entity(
        name: str,
        join_keys: List[str],
        value_type: str = "STRING",
        description: str = "",
        tags: Optional[Dict[str, str]] = None,
    ) -> str:
        """Register an entity (a domain object that feature views are keyed on).

        Args:
            name: Unique name for the entity.
            join_keys: List of join key column names (currently Feast supports one).
            value_type: Type of the join key — STRING, INT64, etc.
            description: Human-readable description.
            tags: Optional metadata tags.
        """
        from feast import Entity, ValueType

        vt_map = {v.name.lower(): v for v in ValueType}
        vt = vt_map.get(value_type.lower(), ValueType.STRING)

        entity = Entity(
            name=name,
            join_keys=join_keys,
            value_type=vt,
            description=description,
            tags=tags or {},
        )
        store.apply([entity])
        return f"Registered Entity '{name}' with join keys {join_keys} (type={vt.name})."

    @tool
    def register_feature_service(
        name: str,
        feature_view_names: List[str],
        description: str = "",
        tags: Optional[Dict[str, str]] = None,
    ) -> str:
        """Register a feature service that groups feature views for serving.

        Args:
            name: Unique name for the feature service.
            feature_view_names: Names of feature views to include.
            description: Human-readable description.
            tags: Optional metadata tags.
        """
        from feast import FeatureService

        fvs = []
        for fv_name in feature_view_names:
            try:
                fvs.append(store.get_feature_view(fv_name))
            except Exception:
                try:
                    fvs.append(store.get_on_demand_feature_view(fv_name))
                except Exception:
                    return f"Error: Feature view '{fv_name}' not found."

        fs = FeatureService(
            name=name,
            features=fvs,
            description=description,
            tags=tags or {},
        )
        store.apply([fs])
        return f"Registered FeatureService '{name}' with views: {feature_view_names}."

    return [
        register_file_source,
        register_bigquery_source,
        register_push_source,
        register_entity,
        register_feature_service,
    ]
