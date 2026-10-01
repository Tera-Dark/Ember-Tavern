# 世界书起步模板 · ember.worldbook/v1

复制 worldbook.json，或在仓库根目录：

```bash
python scripts/creator.py init worldbook creations/my-world --id my-world --name "我的世界"
python scripts/creator.py validate creations/my-world/worldbook.json
```

在宿主 2.2 的「创作工坊」下载／上传 JSON → 校验预览 → 房主确认导入。预览不会写剧情或调用 AI。

## 修改什么

- metadata：作品 id（小写字母开头、字母／数字／连字符、3–48 字符）、名字、三段数字版本、简介、authors、license 和标签。请自己核对授权，不默认授权原作者的文字。
- world：title、premise、tone；rule_system 当前只能为 ember-light/v1。
- lore：地点／NPC 用 kind:lore，桌面约定／规则文字用 kind:rule；visibility:gm 不发玩家，public 可在世界书中阅读。
- enabled:false 完全排除检索；always、关键词 keys、词法匹配与 priority 共同决定上下文。规则／常驻优先，但受总字符／条目预算约束，不承诺整本永远进入模型。
- 为条目填写稳定、唯一的 id（字母／数字／下划线／连字符，最多 64 字符）。合并以 id 更新同条目；缺省 ID 可由宿主补全，但作者应保留稳定 ID。

## 合并与替换

合并保留当前世界标题／前提／风格／扩展，只更新或增加条目；替换改变整本世界书，**不清空已经发生的剧情**。新冒险请新建房间。导入保存事件／快照，可以回档；邀请／成员运营不随剧情回档。

## 边界

- 整个 JSON ≤512 KiB；world 数据的 compact UTF-8 ≤384 KiB、最多 160 条；单条正文 ≤3000 字符，keys ≤24，tags 是最多 120 字符的字符串。
- extensions 用 example.rules/v1 一类版本化命名空间，只存 JSON，不运行规则／脚本；每个扩展容器合计 ≤32 KiB、最多 16 个 namespace。
- 文字规则供 AI 参考，不能改变宿主骰子、属性范围或生命计算；D&D／CoC 等可执行规则适配器需另外开发。
- 世界书导出含主持秘密，且多来源署名许可仍需手工核对；分享前清理。模型不剧透是尽力而为，不是保证。

JSON Schema：registry/worldbook.schema.json。详细语义／旧格式与 ST 子集见 docs/CREATOR_GUIDE.md（路径相对宿主仓库根目录）。CLI 会检查跨字段与大小，不要仅依赖编辑器 Schema。
