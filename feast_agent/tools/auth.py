"""Tools for inspecting and managing Feast RBAC permissions."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from langchain_core.tools import tool

from feast import FeatureStore


def get_auth_tools(store: FeatureStore) -> list:
    """Return all auth/RBAC tools bound to *store*."""

    @tool
    def get_auth_status() -> Dict[str, Any]:
        """Show the current authentication and authorization configuration:
        auth type, whether RBAC permissions are registered, and connectivity mode
        (local vs remote registry)."""
        config = store.config

        auth_info: Dict[str, Any] = {
            "auth_type": getattr(config, "auth", {}).get("type", "no_auth")
            if isinstance(getattr(config, "auth", None), dict)
            else str(getattr(getattr(config, "auth_config", None), "type", "no_auth")),
            "project": config.project,
            "provider": config.provider,
        }

        reg = config.registry
        if isinstance(reg, str):
            auth_info["registry_type"] = "file"
            auth_info["registry_path"] = reg
        elif hasattr(reg, "registry_type"):
            auth_info["registry_type"] = reg.registry_type
            if hasattr(reg, "path"):
                auth_info["registry_path"] = reg.path

        try:
            permissions = store.list_permissions()
            auth_info["permissions_count"] = len(permissions)
            auth_info["permissions"] = [p.name for p in permissions]
            auth_info["rbac_active"] = len(permissions) > 0
        except Exception:
            auth_info["permissions_count"] = 0
            auth_info["rbac_active"] = False
            auth_info["note"] = "Could not list permissions (may not be supported by this registry)."

        return auth_info

    @tool
    def list_permissions() -> Dict[str, Any]:
        """List all RBAC permissions registered in the Feast feature store.
        Each permission defines which actions are allowed on which resource
        types, controlled by a policy (role, group, or namespace-based)."""
        try:
            permissions = store.list_permissions()
        except Exception as e:
            return {"error": f"Failed to list permissions: {e}"}

        if not permissions:
            return {
                "count": 0,
                "message": "No permissions registered. When RBAC is active, "
                "this means all access is DENIED by default.",
            }

        result = []
        for perm in permissions:
            entry: Dict[str, Any] = {
                "name": perm.name,
                "types": [t.__name__ for t in perm.types] if getattr(perm, "types", None) else [],
                "actions": [a.value for a in perm.actions] if getattr(perm, "actions", None) else [],
                "tags": dict(getattr(perm, "tags", None) or {}),
            }

            if hasattr(perm, "name_patterns") and perm.name_patterns:
                entry["name_patterns"] = list(perm.name_patterns)

            if hasattr(perm, "policy"):
                policy = perm.policy
                policy_info: Dict[str, Any] = {"type": type(policy).__name__}
                if hasattr(policy, "roles"):
                    policy_info["roles"] = list(policy.roles)
                if hasattr(policy, "groups"):
                    policy_info["groups"] = list(policy.groups)
                if hasattr(policy, "namespaces"):
                    policy_info["namespaces"] = list(policy.namespaces)
                entry["policy"] = policy_info

            result.append(entry)

        return {"count": len(result), "permissions": result}

    @tool
    def describe_permission(name: str) -> Dict[str, Any]:
        """Describe a specific RBAC permission in detail.

        Args:
            name: Name of the permission to describe.
        """
        try:
            perm = store.get_permission(name)
        except Exception as e:
            return {"error": f"Permission '{name}' not found: {e}"}

        info: Dict[str, Any] = {
            "name": perm.name,
            "types": [t.__name__ for t in perm.types] if getattr(perm, "types", None) else [],
            "actions": [a.value for a in perm.actions] if getattr(perm, "actions", None) else [],
            "tags": dict(getattr(perm, "tags", None) or {}),
        }

        if hasattr(perm, "name_patterns") and perm.name_patterns:
            info["name_patterns"] = list(perm.name_patterns)
        if hasattr(perm, "required_tags") and perm.required_tags:
            info["required_tags"] = dict(getattr(perm, "required_tags", None) or {})

        if hasattr(perm, "policy"):
            policy = perm.policy
            policy_info: Dict[str, Any] = {"type": type(policy).__name__}
            if hasattr(policy, "roles"):
                policy_info["roles"] = list(policy.roles)
            if hasattr(policy, "groups"):
                policy_info["groups"] = list(policy.groups)
            if hasattr(policy, "namespaces"):
                policy_info["namespaces"] = list(policy.namespaces)
            info["policy"] = policy_info

        return info

    @tool
    def create_permission(
        actions: List[str],
        name: Optional[str] = None,
        resource_types: Optional[List[str]] = None,
        name_patterns: Optional[List[str]] = None,
        roles: Optional[Any] = None,
        groups: Optional[Any] = None,
        namespaces: Optional[List[str]] = None,
        tags: Optional[Dict[str, str]] = None,
    ) -> str:
        """Create and register an RBAC permission.

        Args:
            actions: List of action strings, e.g. ["READ_ONLINE"]. Valid:
                CREATE, DESCRIBE, UPDATE, DELETE, READ_ONLINE, READ_OFFLINE,
                WRITE_ONLINE, WRITE_OFFLINE.
            name: Unique name for the permission. Auto-generated if omitted.
            resource_types: Optional Feast types, e.g. ["FeatureView"].
            name_patterns: Optional regex patterns for resource names.
            roles: List of role name strings, e.g. ["analyst", "admin"].
            groups: List of group name strings.
            namespaces: List of namespace strings.
            tags: Optional metadata tags.
        """
        from feast.permissions.action import AuthzedAction
        from feast.permissions.permission import Permission
        from feast.permissions.policy import AllowAll, RoleBasedPolicy

        def _normalize_string_list(val: Any) -> List[str]:
            """Accept str, list, or dict and always return a flat list of strings."""
            if val is None:
                return []
            if isinstance(val, str):
                return [val]
            if isinstance(val, dict):
                flat: List[str] = []
                for v in val.values():
                    if isinstance(v, list):
                        flat.extend(str(x) for x in v)
                    else:
                        flat.append(str(v))
                return flat
            if isinstance(val, list):
                return [str(x) for x in val]
            return [str(val)]

        role_list = _normalize_string_list(roles)
        group_list = _normalize_string_list(groups)

        action_map = {a.name.lower(): a for a in AuthzedAction}
        resolved_actions = []
        for a in actions:
            key = a.strip().lower()
            if key not in action_map:
                return f"Error: Unknown action '{a}'. Valid: {sorted(action_map.keys())}"
            resolved_actions.append(action_map[key])

        if not name:
            action_slug = "_".join(a.name.lower() for a in resolved_actions)
            role_slug = "_".join(role_list) if role_list else "all"
            name = f"{role_slug}_{action_slug}"

        resolved_types = None
        if resource_types:
            import feast
            type_map = {
                "featureview": feast.FeatureView,
                "ondemandfeatureview": feast.OnDemandFeatureView,
                "streamfeatureview": feast.StreamFeatureView,
                "batchfeatureview": feast.BatchFeatureView,
                "entity": feast.Entity,
                "featureservice": feast.FeatureService,
            }
            resolved_types = []
            for rt in resource_types:
                key = rt.strip().lower().replace("_", "")
                if key not in type_map:
                    return f"Error: Unknown resource type '{rt}'. Valid: {sorted(type_map.keys())}"
                resolved_types.append(type_map[key])

        if role_list:
            policy = RoleBasedPolicy(roles=role_list)
        elif group_list:
            from feast.permissions.policy import GroupBasedPolicy
            policy = GroupBasedPolicy(groups=group_list)
        elif namespaces:
            from feast.permissions.policy import NamespaceBasedPolicy
            policy = NamespaceBasedPolicy(namespaces=namespaces)
        else:
            policy = AllowAll()

        kwargs: dict = {
            "name": name,
            "actions": resolved_actions,
            "policy": policy,
            "tags": tags or {},
        }
        if resolved_types:
            kwargs["types"] = resolved_types
        if name_patterns:
            kwargs["name_patterns"] = name_patterns

        perm = Permission(**kwargs)
        store.apply([perm])

        policy_desc = type(policy).__name__
        if hasattr(policy, "roles"):
            policy_desc += f" (roles={list(policy.roles)})"
        elif hasattr(policy, "groups"):
            policy_desc += f" (groups={list(policy.groups)})"

        return (
            f"Created Permission '{name}': actions={[a.name for a in resolved_actions]}, "
            f"policy={policy_desc}."
        )

    @tool
    def check_connectivity() -> Dict[str, Any]:
        """Verify that the agent can connect to the Feast registry and report
        connection details. Useful for diagnosing remote connectivity issues."""
        config = store.config

        result: Dict[str, Any] = {
            "project": config.project,
            "provider": config.provider,
        }

        reg = config.registry
        if isinstance(reg, str):
            result["registry_type"] = "file"
            result["registry_path"] = reg
        elif hasattr(reg, "registry_type"):
            result["registry_type"] = reg.registry_type
            if hasattr(reg, "path"):
                result["registry_url"] = reg.path
            if hasattr(reg, "is_tls"):
                result["tls"] = reg.is_tls

        try:
            sources = store.list_data_sources()
            result["connected"] = True
            result["data_sources_found"] = len(sources)
        except Exception as e:
            result["connected"] = False
            result["error"] = str(e)

        auth_type = "no_auth"
        try:
            auth_config = config.auth_config
            auth_type = str(getattr(auth_config, "type", "no_auth"))
        except Exception:
            pass
        result["auth_type"] = auth_type

        return result

    return [
        get_auth_status,
        list_permissions,
        describe_permission,
        create_permission,
        check_connectivity,
    ]
