# 剧本罗盘：不改宿主的只读扩展

使用 `core.campaign/v1`，只申请 `read:room`。没有 Python、网络、宿主 DOM、会话令牌、骰子或状态写入能力。资源只返回当前场景、目标与已揭示线索，不给只读扩展发送 GM 指引或整个未来剧本。

```bash
python scripts/creator.py init plugin-campaign creations/my-compass --id my-compass
python scripts/creator.py validate creations/my-compass
python scripts/plugins.py package creations/my-compass my-compass.zip
```

作品需要自己的作者 / 许可声明。插件包与数据预设分别打包、审阅与安装；预设 ZIP 不允许包含 ui.js。现有来源锁不会自动接纳后来安装的模块：作者在新预设 `plugins` 中声明其精确 ID / 版本 / 散列，并用 `lock-preset --refresh-plugins` 明确取本机版本后创建新房间。

详细教程：`docs/PRESET_AUTHORING.md`、`docs/PLUGIN_SDK.md`。SHA256 是完整性检查，不是安全认证。
