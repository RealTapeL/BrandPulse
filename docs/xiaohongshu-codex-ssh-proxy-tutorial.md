# 服务器 VS Code + Codex 插件联网教程

## 问题
用 VS Code 的 Remote-SSH 连上服务器后，Codex 插件一直转圈/显示网络连接受限，因为服务器本身没法直接访问 OpenAI。

## 环境
- 本地电脑：Clash Verge（端口例如 7897）
- 远程服务器：`<你的服务器IP>`，用户名 `<你的用户名>`
- VS Code 已安装 Remote - SSH 和 Codex 插件

## 核心思路
不折腾服务器上的代理，直接把**本地 Clash Verge 的代理端口通过 SSH 隧道转发到服务器**，让服务器上的 Codex 走本地代理出国。

## 操作步骤

### 1. 确认本地 Clash Verge 可用
打开 Clash Verge，确认：
- 系统代理或 Clash 服务已启动
- 端口是 `<你的Clash端口>`（设置里能看到，常见如 7890 / 7897 / 10809）
- 节点能正常访问 Google / OpenAI

### 2. 配置 SSH 转发
编辑本地电脑的 `~/.ssh/config`，在对应 Host 里加一行 `RemoteForward`：

```ssh
Host <你的服务器IP>
  HostName <你的服务器IP>
  User <你的用户名>
  RemoteForward <你的Clash端口> 127.0.0.1:<你的Clash端口>
```

`RemoteForward <你的Clash端口> 127.0.0.1:<你的Clash端口>` 的意思：
- 服务器上的 `127.0.0.1:<你的Clash端口>` 被映射到本地电脑的 `127.0.0.1:<你的Clash端口>`
- 也就是把本地 Clash Verge 的代理端口“搬”到了服务器本地

### 3. 配置 VS Code 远程代理
1. 用 VS Code 重新连接服务器
2. 按 `Ctrl + Shift + P`
3. 输入并打开 `Preferences: Open Remote Settings (JSON)`
4. 粘贴以下内容并保存：

```json
{
  "http.proxy": "http://127.0.0.1:<你的Clash端口>",
  "http.proxyStrictSSL": false,
  "http.proxySupport": "override"
}
```

### 4. 重启 VS Code 远程窗口
1. 关闭当前远程 VS Code 窗口
2. 重新 SSH 连接服务器
3. 按 `Ctrl + Shift + P` → `Developer: Reload Window` 重载窗口

## 验证
在服务器终端里执行：

```bash
curl -x http://127.0.0.1:<你的Clash端口> -I --max-time 10 https://api.openai.com
```

如果能看到 `HTTP/1.1 200 Connection established`，说明代理转发成功。

然后打开 Codex 面板，随便发一句话，应该就能正常回复了。

## 常见问题

### Q1: 为什么不用 TUN 模式？
服务器上开 Clash 的 TUN 模式会劫持整个系统的 DNS 和路由，容易导致：
- 系统提示“网络连接受限”
- git 连不上 GitHub
- 国内网站访问异常

用 SSH RemoteForward + VS Code 代理设置只对 VS Code 生效，不会影响服务器其他功能。

### Q2: 还是连不上？
检查这几点：
1. 本地 Clash Verge 端口到底是不是 `<你的Clash端口>`
2. SSH 重连后，服务器上 `127.0.0.1:<你的Clash端口>` 是否已监听：`netstat -tlnp | grep <你的Clash端口>`
3. 本地 Clash 节点是否真的能访问 OpenAI
4. VS Code Remote Settings 是不是填成了用户设置而不是远程设置

### Q3: 端口冲突怎么办？
如果服务器上 <你的Clash端口> 被占用，可以换端口，例如：

```ssh
RemoteForward <服务器端备用端口> 127.0.0.1:<你的Clash端口>
```

同时 VS Code 设置里也改成：

```json
"http.proxy": "http://127.0.0.1:<服务器端备用端口>"
```

## 总结
- 服务器不要直接跑 Clash TUN
- 用 `RemoteForward` 把本地代理端口透传到服务器
- VS Code 远程设置里指定 `http.proxy`
- Codex 就能正常连 OpenAI 了
