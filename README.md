# Jira Readonly MCP Server

一个基于 Python `mcp` SDK 和 Jira Data Center REST API 的只读远程 MCP Server。

它通过 `streamable-http` 暴露 MCP 端点，适合同机本地联调，也可以在受控网络环境中作为远程 MCP 服务运行。

## 功能

当前版本只提供 3 个只读工具：

- `whoami`：验证 Jira 连通性与请求中的 PAT 是否可用
- `search_issues`：按 JQL 查询 issue，支持分页和字段白名单
- `get_issue`：按 issue key 或数值 id 读取单票详情

## 特性

- 基于官方 Python `mcp` SDK
- 使用 Jira Data Center PAT 认证
- 从 MCP 客户端传入的 `Authorization` 头透传 Jira PAT
- 仅暴露只读工具，不包含写操作
- 对 `fields`、`expand` 和 `max_results` 做服务端限制
- 默认只监听 `127.0.0.1`，更适合同机测试

## 要求

- Python `3.11+`
- `uv`
- 一个可访问目标 Jira Data Center 的运行环境
- 一个有效的 Jira Personal Access Token

## 安装

```bash
uv sync
```

## 配置

先复制示例配置：

```bash
cp .env.example .env
```

至少需要修改这一项：

- `JIRA_BASE_URL`

如需使用 `.env` 文件启动，先在当前 shell 中加载：

```bash
set -a
source .env
set +a
```

### 主要环境变量

必填：

```bash
export JIRA_BASE_URL="https://jiradc.example.com"
```

常用可选项：

```bash
export JIRA_REST_PREFIX="/rest/api/2"
export JIRA_TIMEOUT_SECONDS="15"
export JIRA_VERIFY_SSL="true"
export JIRA_MAX_RESULTS="25"
export MCP_HOST="127.0.0.1"
export MCP_PORT="8000"
export MCP_PATH="/mcp"
```

完整示例见 [`.env.example`](.env.example)。

### Codex MCP 客户端配置

Jira PAT 不再通过服务端环境变量注入，而是由 MCP 客户端在每次请求中携带 `Authorization` 头。

例如，在 `~/.codex/config.toml` 中配置：

```toml
[mcp_servers.jira]
url = "http://127.0.0.1:8000/mcp"

[mcp_servers.jira.http_headers]
Authorization = "Bearer your_jira_pat"
```

如果服务是远程部署的，把 `url` 改成你的远程 MCP 地址即可，例如：

```toml
[mcp_servers.jira]
url = "https://your-mcp-server.example.com/mcp"

[mcp_servers.jira.http_headers]
Authorization = "Bearer your_jira_pat"
```

如果未配置该 Header，`whoami`、`search_issues` 和 `get_issue` 会直接返回缺少鉴权头的错误。

## 运行

任选一种：

```bash
uv run jira-mcp
```

```bash
uv run python main.py
```

```bash
uv run python -m jira_mcp
```

默认监听地址：

```text
http://127.0.0.1:8000/mcp
```

## 工具说明

### `whoami`

返回当前 Jira 用户信息，用于验证：

- 请求中的 PAT 是否有效
- Jira REST API 是否可达
- 当前身份是否与预期一致

### `search_issues`

输入参数：

- `jql`
- `start_at`
- `max_results`
- `fields`

约束：

- `max_results` 会被硬限制到 `JIRA_MAX_RESULTS`
- `fields` 只能使用允许的白名单字段

### `get_issue`

输入参数：

- `issue_key`
- `fields`
- `expand`

约束：

- `issue_key` 必须是合法 Jira issue key 或数值 id
- `fields` 只能使用允许的白名单字段
- `expand` 当前仅允许 `names` 和 `schema`

## 本地测试

如果 `MCP client` 和 `MCP server` 在同一台机器或同一测试环境中，不需要反向代理，直接连接本地地址即可。

推荐本地配置：

```bash
export MCP_HOST="127.0.0.1"
export MCP_PORT="8000"
export MCP_PATH="/mcp"
```

最小验证顺序：

1. 启动服务
2. 在 `~/.codex/config.toml` 中配置 MCP 地址和 `Authorization` 头
3. 连接 `http://127.0.0.1:8000/mcp`
4. 调用 `whoami`
5. 调用 `search_issues`
6. 调用 `get_issue`

## 已验证场景

当前项目已完成以下验证：

- Jira `/rest/api/2/myself` 连通性验证
- MCP `initialize`
- MCP `tools/list`
- `whoami`
- `search_issues`
- `get_issue`

本地同机模式已在 Codex 中验证通过。

## Jira 认证方式

Jira Data Center PAT 使用 Bearer Token，并由 MCP 客户端透传给服务端：

```http
Authorization: Bearer <PAT>
```

## 安全说明

- 这是只读 MCP Server，不暴露写操作工具。
- PAT 不应写入代码，也不要提交到仓库。
- 建议使用权限受限的只读账号生成 PAT。
- MCP Server 本身不保存 Jira PAT，而是使用客户端请求中传入的 `Authorization` 头访问 Jira。
- 默认只监听 `127.0.0.1`。如果需要远程部署，请显式设置 `MCP_HOST`，并放在反向代理、内网 ACL 或其他鉴权层后面。
- 如果 Jira 使用企业 CA 或自签名证书，应正确配置 TLS 校验链，而不是长期关闭 SSL 校验。

## 上传到 GitHub 前

建议在推送前确认以下几点：

- `.env` 和 `.env.local` 没有被提交
- 仓库中没有真实 Jira 地址、真实 PAT、个人邮箱或内部截图
- `README`、`.env.example` 只保留示例值
- 如需公开发布，优先使用通用示例域名，例如 `https://jiradc.example.com`

目前仓库已经通过 `.gitignore` 忽略了本地环境文件：

- `.env`
- `.env.local`
