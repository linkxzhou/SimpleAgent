# Spec: TODO API 项目

## 概述

一个完整的 TODO REST API 项目，使用 Python + Flask 实现。
项目应可独立运行、有清晰的目录结构、包含完整的 pytest 测试。

## 功能需求

### 数据模型

- TODO 项包含字段：`id`（整数，自增）、`title`（字符串，必填）、`done`（布尔值，默认 False）
- 使用内存存储（Python 字典/列表），无需数据库

### API 路由

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /todos | 获取所有 TODO 项 |
| GET | /todos/<id> | 获取单个 TODO 项 |
| POST | /todos | 创建新 TODO 项（body: `{"title": "..."}`) |
| PUT | /todos/<id> | 更新 TODO 项（body: `{"title": "...", "done": true}`) |
| DELETE | /todos/<id> | 删除 TODO 项 |

### 响应格式

- 成功：返回 JSON 数据 + 适当的 HTTP 状态码（200/201/204）
- 未找到：返回 `{"error": "not found"}` + 404
- 参数错误：返回 `{"error": "title is required"}` + 400

## 项目结构

```
todo_api/
├── app.py              # Flask 应用 + 路由定义
├── requirements.txt    # 依赖（flask, pytest）
└── test_app.py         # pytest 测试（覆盖所有路由和错误场景）
```

## 测试要求

- 使用 Flask test client，不需要启动真实服务器
- 每个路由至少 2 个测试（正常 + 异常）
- 最终 `pytest test_app.py` 全部通过

## 约束

- 纯 Python 标准库 + Flask + pytest，不使用其他框架
- 单文件 app.py 即可，不需要蓝图或工厂模式
- 代码风格简洁清晰，有必要的注释
