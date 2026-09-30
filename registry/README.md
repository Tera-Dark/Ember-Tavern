# 插件索引发布模板

index.json 当前是本地发行清单，github_repository 为真实项目地址，download_url 只在实际 Release 发布后填写。不是在线插件市场，不包含虚构仓库／下载量。

拥有者创建 GitHub 仓库、发布真实 Release 后，填入对应 HTTPS URL 和**该实际资产**的 SHA256。保留 api_version、capabilities、backend 与审核状态；禁止把“校验过哈希”写成“安全无风险”。未来可加签名、兼容矩阵、撤销清单与审核者记录；当前不实现自动拉取／执行。
