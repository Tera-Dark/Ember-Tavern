# 场景便签 · 受信任 Python 插件示例

演示 SDK 的 Extension.action / Result、房主权限、独立 namespace、事件快照、前端 invoke。默认关闭。仅提供代码示例，不会被宿主自动发现或执行 templates 下的 Python。

```bash
python scripts/plugins.py package templates/scene-notes plugin-packages/scene-notes-1.0.0.zip
# 审阅 backend.py，再显式信任：
python scripts/plugins.py install plugin-packages/scene-notes-1.0.0.zip --sha256 <实际SHA256> --trust-backend
```

不要把 --trust-backend 用于未审核第三方代码；Python 不是沙箱。发布前确定许可证。
