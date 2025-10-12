#!/usr/bin/env python3
"""
LLM Gateway 基础测试
用于验证核心功能是否正常工作
"""

import pytest
import asyncio
from app import app, RateLimiter
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """创建测试客户端"""
    return TestClient(app)


class TestRateLimiter:
    """速率限制器测试类"""
    
    def setup_method(self):
        """每个测试方法前重置速率限制器"""
        self.rate_limiter = RateLimiter()
    
    def test_check_limit_basic(self):
        """测试基础速率限制检查"""
        api_provider = "test_provider"
        limits = {"rpm": 10, "tpm": 1000}
        
        # 第一次检查应该通过
        result, reason = self.rate_limiter.check_limit(api_provider, limits)
        assert result is True
        assert reason == ""
        
        # 增加计数
        self.rate_limiter.increment(api_provider, 100)
        
        # 再次检查应该仍然通过
        result, reason = self.rate_limiter.check_limit(api_provider, limits)
        assert result is True
        assert reason == ""
    
    def test_rpm_limit(self):
        """测试RPM限制"""
        api_provider = "test_provider"
        limits = {"rpm": 2}
        
        # 前两次应该通过
        for i in range(2):
            result, reason = self.rate_limiter.check_limit(api_provider, limits)
            assert result is True
            self.rate_limiter.increment(api_provider)
        
        # 第三次应该被限制
        result, reason = self.rate_limiter.check_limit(api_provider, limits)
        assert result is False
        assert "RPM limit exceeded" in reason
    
    def test_tpm_limit(self):
        """测试TPM限制"""
        api_provider = "test_provider"
        limits = {"tpm": 500}
        
        # 第一次请求，消耗300 tokens
        result, reason = self.rate_limiter.check_limit(api_provider, limits, 300)
        assert result is True
        self.rate_limiter.increment(api_provider, 300)
        
        # 第二次请求，消耗250 tokens，应该通过
        result, reason = self.rate_limiter.check_limit(api_provider, limits, 250)
        assert result is True
        
        # 第三次请求，消耗100 tokens，应该被限制
        result, reason = self.rate_limiter.check_limit(api_provider, limits, 100)
        assert result is False
        assert "TPM limit exceeded" in reason


class TestAPIEndpoints:
    """API端点测试类"""
    
    def test_models_endpoint(self, client):
        """测试/models端点"""
        response = client.get("/v1/models")
        assert response.status_code == 200
        data = response.json()
        assert "object" in data
        assert "data" in data
        assert isinstance(data["data"], list)
    
    def test_api_usage_endpoint(self, client):
        """测试/api_usage端点"""
        response = client.get("/api_usage")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "timestamp" in data
    
    def test_config_endpoint(self, client):
        """测试配置端点"""
        # 测试获取配置
        response = client.get("/api/config")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        
        # 测试更新配置（需要有效的配置数据）
        # 这里只测试端点存在性，不测试具体逻辑
        response = client.post("/api/config", json={})
        assert response.status_code == 200
    
    def test_admin_endpoint(self, client):
        """测试管理界面端点"""
        response = client.get("/admin")
        assert response.status_code == 200
        # 应该返回HTML内容
        assert "text/html" in response.headers["content-type"]
    
    def test_error_logs_endpoint(self, client):
        """测试错误日志端点"""
        response = client.get("/api/error_logs")
        assert response.status_code == 200
        data = response.json()
        assert "error_logs" in data
        assert isinstance(data["error_logs"], list)


def test_app_initialization():
    """测试应用初始化"""
    # 确保应用正确创建
    assert app is not None
    assert hasattr(app, 'routes')
    
    # 检查关键路由是否存在
    routes = [route.path for route in app.routes]
    assert "/v1/{path:path}" in routes
    assert "/api_usage" in routes
    assert "/v1/models" in routes


if __name__ == "__main__":
    # 运行基础测试
    pytest.main([__file__, "-v"])
