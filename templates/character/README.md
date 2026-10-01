# 角色卡起步模板 · ember.character/v1

```bash
python scripts/creator.py init character creations/my-character --id my-character --name "我的角色卡"
python scripts/creator.py validate creations/my-character/character.json
```

在「创作工坊」预览，由房主确认后新建角色；宿主生成新角色 ID，不带任何账号、房间或操控权。然后去「角色档案」分配给同伴。模板是轻规则角色，不是聊天人格或 PNG 卡。

## 字段

- metadata：作品 ID／名字／版本／作者／许可；替换示例信息，自行确认分享权利。
- rule_system 当前只能为 ember-light/v1。导入卡与所在房间的可执行规则必须一致。
- character.name／archetype／description 是公开资料；gm_notes 是主持秘密，玩家 REST／WS／普通插件上下文不收到。角色导出可能包含 gm_notes，分享前删除。
- hp 0–100 且不超过 max_hp；max_hp 1–100；stress 0–6。
- attributes：strength、dexterity、knowledge、insight、charisma，整数 -3…5；inventory 最多 24 个物品，每项 1–60 字符。
- avatar 只能为 feather／shield／sword／book／spark；图片美术、URL、完整 D&D 数据结构不是本版原生字段。
- 不要添加 assigned_to、owner_id 或权限字段；未知字段拒绝。附加系统数据放版本化 extensions，例如 example.equipment/v1，只存 JSON，默认不是私密仓库。

整个 JSON ≤512 KiB；extensions 合计 ≤32 KiB、最多 16 个 namespace，有限深度。卡片导入为新角色、不会覆盖现有角色；资料编辑会保留已有扩展。作者仍需给扩展实现有版本的解释模块。

JSON Schema：registry/character.schema.json；完整指引 docs/CREATOR_GUIDE.md（相对宿主根目录）。CLI 校验不改写源文件，也不会执行代码。
