"""配置验证工具 - 验证字典配置的必需字段和类型。"""

from typing import Dict, Any, List, Optional


def validate_config(config: Any, required_fields: Dict[str, type]) -> Dict[str, Any]:
    """验证配置字典是否包含所有必需字段且类型正确。
    
    Args:
        config: 待验证的配置（应为 dict）
        required_fields: 必需字段及其期望类型的字典，如 {"name": str, "port": int}
    
    Returns:
        {"valid": bool, "errors": List[str]}
        
    Examples:
        >>> validate_config({"name": "app", "port": 8080}, {"name": str, "port": int})
        {"valid": True, "errors": []}
        
        >>> validate_config({"name": "app"}, {"name": str, "port": int})
        {"valid": False, "errors": ["Missing required field: port"]}
    """
    errors: List[str] = []
    
    # 检查输入是否为字典
    if not isinstance(config, dict):
        return {
            "valid": False,
            "errors": [f"Config must be a dict, got {type(config).__name__}"]
        }
    
    # 检查必需字段
    for field_name, expected_type in required_fields.items():
        if field_name not in config:
            errors.append(f"Missing required field: {field_name}")
            continue
        
        # 检查字段类型
        value = config[field_name]
        if not isinstance(value, expected_type):
            errors.append(
                f"Field '{field_name}' has wrong type: "
                f"expected {expected_type.__name__}, got {type(value).__name__}"
            )
    
    return {
        "valid": len(errors) == 0,
        "errors": errors,
    }
