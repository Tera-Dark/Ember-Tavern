# 标准创作起步模板

当前源码元数据：宿主 / 网页 2.4.0-beta.1、桌面 / 部署引擎 0.2.0-beta.3、Plugin API 1。公开桌面 Release 仍是旧版 0.2.0-beta.1 / 宿主 2.3.0-beta.1；本轮 M2 改动尚未随二进制发布，详情见 [M2 交付记录](../docs/M2_DELIVERY.md)。世界、角色、主题是**数据**，插件代码与信任单独处理。

| 目录 | CLI init 类型 | 文件／行为 |
| --- | --- | --- |
| worldbook | worldbook | ember.worldbook/v1；公共地点、桌面约定、主持秘密 |
| character | character | ember.character/v1；5 项轻规则属性、背包、主持备注；无操控权 |
| theme | theme | ember.theme/v1；dark／light 的 15 个六位颜色令牌 |
| session-insights | plugin-ui | 独立只读 UI，read:room／read:events |
| scene-notes | plugin-backend | 可信 Python Result／namespace／回档示例 |
| dice-tray | plugin-dice | UI → EmberSDK.roll → 服务器自由骰；最低宿主 2.2.0 |

```bash
python scripts/creator.py init worldbook creations/my-world --id my-world --name "我的世界"
python scripts/creator.py validate creations/my-world/worldbook.json
python scripts/creator.py init plugin-dice creations/my-dice --id my-dice
python scripts/creator.py validate creations/my-dice
```

不覆盖现有作品、不执行 backend；初始化清单默认关闭社区模块，并清空示例署名／许可。请填真实 metadata 和授权信息。`creations/` 草稿默认不入 Git／镜像；对外发布移到自己的作品仓库并去掉秘密。模板不代表自动获得项目或他人素材许可证，项目 LICENSE 仍需拥有者确定。

CLI、安装器、运行时与 `registry/*.schema.json` 共用契约；跨字段与字节上限以运行时校验为准。插件最少申请能力，read:gm 也需明确 grant，Python 需代码审核／trust-backend；hash 不是安全认证。

完整教程：[CREATOR_GUIDE](../docs/CREATOR_GUIDE.md)；模块生命周期／能力／资源：[PLUGIN_SDK](../docs/PLUGIN_SDK.md)。

## M1 完整玩法组合

以下是源码中的作者模板与流程；公开旧版桌面包不含当前分支的 M2 能力。

- `preset/`：世界书＋剧本＋四张角色＋精确模块引用与说明。`creator.py init preset` / `lock-preset` / `package-preset`。
- `scenario/`：有限场景、线索前置条件与结局；不包含可执行脚本。
- `campaign-compass/`：独立只读 UI，用 core.campaign/v1 显示公开进度，单独安装，不放进预设 ZIP。

完整教程：`docs/PRESET_AUTHORING.md`。模板不是已授权社区发行作品，填写署名／许可再分享。
