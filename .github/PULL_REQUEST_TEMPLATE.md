## 改动与插件契约
- 插件 ID、版本、API／schema 版本：
- requires／uses／provides／hooks／capabilities 的变更：
- 用户可见效果与截图：

## 安全与状态
- [ ] 无密钥／token／生产数据，用户文本安全转义
- [ ] Python／高风险能力已标记供部署者审查
- [ ] 权限、关闭保留、回档、分支与并发冲突已测试
- [ ] 修改内置插件后，仅在完整审核之后更新 catalog.lock.json
- [ ] API 不兼容／状态迁移已写明，不静默覆盖

## 验证
- [ ] pytest / frontend build
- [ ] 相应双浏览器测试或说明为何不适用
- [ ] 外部服务的 Mock 与真实测试明确区分
