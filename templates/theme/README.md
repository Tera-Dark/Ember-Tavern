# 个人主题起步模板 · ember.theme/v1

```bash
python scripts/creator.py init theme creations/my-theme --id my-theme --name "我的配色"
python scripts/creator.py validate creations/my-theme/theme.json
```

修改 metadata 与 modes，再到「创作工坊」校验／应用。当前只作用本浏览器，不写房间 revision、不改变朋友的界面或剧情，并把已批准的颜色传递给隔离插件。可恢复默认配色。

## 设计令牌

至少包含 dark／light 中一种；每种包含全部 15 个令牌，每个值为 #RRGGBB：

- --bg、--surface、--surface-2、--surface-3、--border
- --text、--muted、--faint
- --gold、--gold-hover、--gold-bg
- --green、--green-bg、--red、--red-bg

gold 是强调色，不要求实际为金色。注意文字／背景对比、禁用态／错误态可辨识；不要单靠颜色传递重要信息。模式切换时未提供的另一种使用宿主默认配色。

**不接受任意 CSS、脚本、HTML、URL、字体或背景图片。** 美术素材／完整皮肤是后续模块能力，不能用本模板绕开 iframe 或请求权限。作品 ID 与版本规则见创作指南；整个 JSON ≤512 KiB，未知字段拒绝。

JSON Schema：registry/theme.schema.json；完整指引 docs/CREATOR_GUIDE.md（相对宿主根目录）。使用模板不等于已获得所有素材或品牌许可，请填写自己的作者／许可并核对分享范围。
