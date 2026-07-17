# Tests

跨前后端的端到端测试目录。

前端组件测试放在 `frontend/`，后端单元和集成测试放在 `backend/tests/`，完整用户流程放在 `tests/e2e/`。

当前可重复的 Fixture MVP 流程测试位于 `backend/tests/integration/test_mvp_fixture_flow.py`，覆盖健康检查、列表/详情、日志、资源统计、提交、取消、克隆和摘要。后续浏览器自动化工具确定后，再将同一故事补充到 `tests/e2e/`，不重复创建测试框架。
