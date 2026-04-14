"""Tools for creating on-demand feature views with transformations."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from langchain_core.tools import tool

from feast import FeatureStore

from feast_agent.tools.registry import _resolve_feast_type


def get_transformation_tools(store: FeatureStore) -> list:
    """Return all transformation tools bound to *store*."""

    @tool
    def create_on_demand_feature_view(
        name: str,
        source_feature_view_names: List[str],
        schema_fields: List[Dict[str, str]],
        transformation_code: str,
        mode: str = "pandas",
        request_schema_fields: Optional[List[Dict[str, str]]] = None,
        description: str = "",
        tags: Optional[Dict[str, str]] = None,
    ) -> str:
        """Create an OnDemandFeatureView with an inline transformation.

        The transformation_code must define a function body that takes a
        pandas DataFrame (for mode='pandas') or a dict (for mode='python')
        named 'inputs' and returns the transformed result.

        Example transformation_code for mode='pandas':
            "import pandas as pd\\ndf = inputs\\ndf['ratio'] = df['a'] / df['b']\\nreturn df"

        Args:
            name: Unique name for the on-demand feature view.
            source_feature_view_names: Names of existing feature views whose
                features will be inputs to this transformation.
            schema_fields: Output schema — list of {"name": "col", "dtype": "Float64"}.
            transformation_code: Python code for the transformation function body.
            mode: Transformation mode — 'pandas' or 'python'.
            request_schema_fields: Optional request-time input fields as
                [{"name": "col", "dtype": "Float64"}]. Use when the transform
                needs data supplied at request time.
            description: Human-readable description.
            tags: Optional metadata tags.
        """
        from feast import Field, OnDemandFeatureView, RequestSource

        sources = []
        for fv_name in source_feature_view_names:
            try:
                sources.append(store.get_feature_view(fv_name))
            except Exception:
                try:
                    sources.append(store.get_on_demand_feature_view(fv_name))
                except Exception:
                    return f"Error: source feature view '{fv_name}' not found."

        if request_schema_fields:
            req_fields = []
            for f in request_schema_fields:
                feast_type = _resolve_feast_type(f["dtype"])
                req_fields.append(Field(name=f["name"], dtype=feast_type))
            sources.append(RequestSource(name=f"{name}_request", schema=req_fields))

        output_fields = []
        for f in schema_fields:
            feast_type = _resolve_feast_type(f["dtype"])
            output_fields.append(Field(name=f["name"], dtype=feast_type))

        func_name = f"_odfv_{name}_transform"
        if mode == "pandas":
            full_code = (
                f"def {func_name}(inputs):\n"
                + "\n".join(f"    {line}" for line in transformation_code.split("\n"))
                + "\n"
            )
        else:
            full_code = (
                f"def {func_name}(inputs):\n"
                + "\n".join(f"    {line}" for line in transformation_code.split("\n"))
                + "\n"
            )

        local_ns: dict = {}
        exec(full_code, {"__builtins__": __builtins__}, local_ns)  # noqa: S102
        udf = local_ns[func_name]

        odfv = OnDemandFeatureView(
            name=name,
            sources=sources,
            schema=output_fields,
            udf=udf,
            udf_string=full_code,
            mode=mode,
            description=description,
            tags=tags or {},
        )
        store.apply([odfv])
        return (
            f"Created OnDemandFeatureView '{name}' (mode={mode}) with "
            f"{len(output_fields)} output features, sourced from "
            f"{source_feature_view_names}."
        )

    @tool
    def list_transformation_modes() -> str:
        """List the supported transformation modes for on-demand and batch
        feature views."""
        return (
            "Supported transformation modes:\n"
            "  - pandas: Transform receives/returns a pandas DataFrame\n"
            "  - python: Transform receives/returns a Python dict\n"
            "  - sql: SQL-based transformation\n"
            "  - spark: Apache Spark transformation\n"
            "  - spark_sql: Spark SQL transformation\n"
            "  - ray: Ray-based distributed transformation\n"
            "  - substrait: Substrait/Ibis transformation\n"
            "\n"
            "For OnDemandFeatureView, 'pandas' and 'python' are the most common."
        )

    return [
        create_on_demand_feature_view,
        list_transformation_modes,
    ]
