# 桌面骰盘：宿主命令桥模板

- 纯 UI，无 Python 后端。`EmberSDK.roll(expression)` 调用宿主服务端骰子。
- 清单同时声明 `dice:roll` 和 `uses: ["core.dice/v1"]`；资源及服务端会再次校验。
- 结果带服务端 rolls / modifier / total / request_key，记入普通 `dice` 事件、广播、可回档审计。
- 这是自由掷骰，不接管 pending_check；完整检定仍由规则适配器执行。
- 安装前审阅代码，使用 `--grant-capabilities`。不要在客户端模拟检定结果并当作正史。

```bash
python scripts/plugins.py package templates/dice-tray /tmp/dice-tray.zip
python scripts/plugins.py install /tmp/dice-tray.zip --sha256 <实际SHA256> --grant-capabilities
```
