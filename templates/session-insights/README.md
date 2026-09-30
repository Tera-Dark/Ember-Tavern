# 会话观察板 · 独立 UI 插件示例

复制此目录，改 id/name/group 和 ui.js 即可开始。仅 `read:room`、`read:events`，无 Python、无写权限、无外网。

在宿主根目录：
```bash
python scripts/plugins.py package templates/session-insights plugin-packages/session-insights-1.0.0.zip
python scripts/plugins.py install plugin-packages/session-insights-1.0.0.zip --sha256 <命令输出的SHA256>
```
到模块中心刷新、开启即可出现独立观察板，不修改宿主和前端入口。SDK：`docs/PLUGIN_SDK.md`。发布前由拥有者确定许可证，不要把本项目的 LICENSE.example 当作已授予许可。
