"""Tests for config_validator module."""

import pytest
from src.config_validator import validate_config


class TestValidateConfig:
    """测试 validate_config 函数的各种场景。"""
    
    def test_valid_minimal_config(self):
        """测试最小有效配置。"""
        config = {"name": "test"}
        required = {"name": str}
        result = validate_config(config, required)
        
        assert result["valid"] is True
        assert result["errors"] == []
    
    def test_valid_full_config(self):
        """测试完整有效配置。"""
        config = {
            "name": "myapp",
            "version": "1.0.0",
            "port": 8080,
            "debug": True,
        }
        required = {
            "name": str,
            "version": str,
            "port": int,
            "debug": bool,
        }
        result = validate_config(config, required)
        
        assert result["valid"] is True
        assert result["errors"] == []
    
    def test_missing_required_field_name(self):
        """测试缺少必需字段 name。"""
        config = {"version": "1.0.0"}
        required = {"name": str, "version": str}
        result = validate_config(config, required)
        
        assert result["valid"] is False
        assert "Missing required field: name" in result["errors"]
    
    def test_missing_required_field_version(self):
        """测试缺少必需字段 version。"""
        config = {"name": "app"}
        required = {"name": str, "version": str}
        result = validate_config(config, required)
        
        assert result["valid"] is False
        assert "Missing required field: version" in result["errors"]
    
    def test_missing_both_required_fields(self):
        """测试缺少多个必需字段。"""
        config = {"other": "value"}
        required = {"name": str, "version": str}
        result = validate_config(config, required)
        
        assert result["valid"] is False
        assert len(result["errors"]) == 2
        assert "Missing required field: name" in result["errors"]
        assert "Missing required field: version" in result["errors"]
    
    def test_wrong_type_name(self):
        """测试字段类型错误（name 应为 str 但给了 int）。"""
        config = {"name": 123, "version": "1.0.0"}
        required = {"name": str, "version": str}
        result = validate_config(config, required)
        
        assert result["valid"] is False
        assert any("Field 'name' has wrong type" in err for err in result["errors"])
        assert any("expected str, got int" in err for err in result["errors"])
    
    def test_wrong_type_port(self):
        """测试字段类型错误（port 应为 int 但给了 str）。"""
        config = {"name": "app", "port": "8080"}
        required = {"name": str, "port": int}
        result = validate_config(config, required)
        
        assert result["valid"] is False
        assert any("Field 'port' has wrong type" in err for err in result["errors"])
        assert any("expected int, got str" in err for err in result["errors"])
    
    def test_optional_field_missing_is_ok(self):
        """测试可选字段缺失不影响验证（只验证必需字段）。"""
        config = {"name": "app"}  # 没有 optional_field
        required = {"name": str}  # 不要求 optional_field
        result = validate_config(config, required)
        
        assert result["valid"] is True
        assert result["errors"] == []
    
    def test_not_dict_input(self):
        """测试输入不是字典时返回错误。"""
        config = "not a dict"
        required = {"name": str}
        result = validate_config(config, required)
        
        assert result["valid"] is False
        assert "Config must be a dict, got str" in result["errors"]
    
    def test_empty_dict_with_required_fields(self):
        """测试空字典但有必需字段要求。"""
        config = {}
        required = {"name": str, "version": str}
        result = validate_config(config, required)
        
        assert result["valid"] is False
        assert len(result["errors"]) == 2
    
    def test_none_input(self):
        """测试 None 输入。"""
        config = None
        required = {"name": str}
        result = validate_config(config, required)
        
        assert result["valid"] is False
        assert "Config must be a dict, got NoneType" in result["errors"]
    
    def test_list_input(self):
        """测试列表输入。"""
        config = ["not", "a", "dict"]
        required = {"name": str}
        result = validate_config(config, required)
        
        assert result["valid"] is False
        assert "Config must be a dict, got list" in result["errors"]
