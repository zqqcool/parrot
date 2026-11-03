# Parrot Runtime Operations Runbook

## Boundary

Parrot is the only deployable application and `/api/v1` is the only browser-facing API root. The
retained `skyler/` directory is read-only migration source material. Do not import its modules,
mount its routers, reuse identity headers, access its database, or configure it as a runtime
fallback.

The production runtime is `in_process`: the WebSocket IM adapter persists an immutable interaction/profile snapshot,
commits its runtime execution metadata, then directly publishes a tenant-scoped TaskIQ Redis Stream task. That task holds a PostgreSQL
lease and writes durable `ai.*` events before WebSocket publication. The same TaskIQ registry delivers
schedules, memory indexing, knowledge ingestion/indexing, and Skill builds; domain modules do not
run their own polling workers.

The accepted Web transaction does not create a placeholder runtime lease for the local durable path.
The TaskIQ worker's first successful claim is the first lease assignment. A zero-second lease is not
equivalent to no lease: immediate delivery can observe the same database timestamp and silently miss
the strict expiry predicate after the Redis message has already been acknowledged.

The generic Agent Loop does not require `tool_choice=required`. OpenAI-compatible endpoints may expose
tool calling while rejecting that mode when reasoning is enabled. Structured terminal tools remain
available, but ordinary assistant text is a valid terminal fallback. Streaming HTTP error bodies must
be read before classification so provider failures remain `AI_PROVIDER_UNAVAILABLE` rather than being
masked by a local `ResponseNotRead` error.

## Required production configuration

```toml
[runtime]
default_timezone = "Asia/Shanghai"

[schedules]
default_timezone = "Asia/Shanghai"

[taskiq]
queue_name = "parrot:tasks"
consumer_group = "parrot"
schedule_prefix = "parrot:schedules"
# Used only for delayed background delivery; real-time interactions are direct.
dispatch_delay_seconds = 3
stream_maxlen = 100000
unacknowledged_idle_seconds = 600

[runtime.script]
enabled = false

[ai]
allowed_model_hosts = ["models.example.com"]
debug_log_prompts = false # dev/SIT diagnostic; prod rejects true
debug_capture_prompts = false # dev/SIT Run prompt snapshots; prod rejects true
agent_max_tool_rounds = 6
agent_max_tool_calls = 12
agent_max_consecutive_tool_errors = 3
agent_max_output_tokens = 4096
agent_model_retry_attempts = 2
agent_max_control_plane_replans = 2
agent_max_finalization_replans = 1
agent_direct_rendering_enabled = true
agent_loop_subagents_enabled = true
max_parallel_tool_calls = 3
capability_exact_repeat_limit = 1
capability_similar_repeat_limit = 2
capability_similarity_threshold = 0.6

[security]
credential_encryption_key = "overridden-by-external-secrets"

[memory.vector]
enabled = false
uri = "https://milvus.example.com"
token_ref = "memory-vector-token"

[memory.embedding]
base_url = "https://embeddings.example.com/v1"
model = "embedding-model"
credential_ref = "embedding-key"
allowed_hosts = ["embeddings.example.com"]
# Provider-specific, non-secret options; keep the returned dimension aligned with memory.vector.
extra_body = { dimensions = 1024, encoding_format = "float" }

[knowledge.embedding]
allowed_hosts = ["knowledge-embeddings.example.com"]
timeout_seconds = 30

[knowledge.reranker]
allowed_hosts = ["knowledge-rerankers.example.com"]
timeout_seconds = 30

[knowledge.vector]
uri = "https://knowledge-milvus.example.com"
collection = "parrot_knowledge"
token_ref = "knowledge-vector-token"

# During the MVP these values live in the selected complete deployment TOML.
# They must remain disposable test credentials and be externalized before real production use.
[memory_credentials.values]
memory-vector-token = "replace-with-milvus-token"
embedding-key = "replace-with-embedding-provider-key"

[knowledge_credentials.values]
knowledge-vector-token = "replace-with-knowledge-milvus-token"
```

两个 Agent Runtime 开关用于灰度和回滚，不改变持久化合同：

- `agent_direct_rendering_enabled=false`：功能型 direct answer 回到私有候选路径；知识合成和 TaskBoard 汇总仍使用
  Renderer，因为它们没有可继续执行的 Agent Loop。
- `agent_loop_subagents_enabled=false`：只隐藏普通 Root Loop 中的 `subagent_dispatch` Tool；保留已有 Planner 入口
  Subagent。这样可单独回滚新入口，不破坏原有功能型 Planner 场景。

修改开关后必须重启 TaskIQ worker；Web 进程不执行 Agent Loop。Run 管理诊断中的 `runtime.milestone` 提供
`provider_first_content_delta`、`public_first_delta` 和 `run_completed` 的相对 `elapsed_ms`。灰度时应使用相同 Agent、
模型、输入和知识数据对比 p50/p95，不能用单次本地 Fake Provider 耗时替代真实端点结论。

真实 WebSocket 端点可以使用仓库脚本采样：

```bash
backend/.venv/bin/python scripts/benchmark_interaction_websocket.py \
  --url 'ws://127.0.0.1:8000/api/v1/im/ws/<channel-key>' \
  --origin 'http://127.0.0.1:5173' \
  --prompt '<固定且不含敏感数据的问题>' \
  --label '<小写基线标签>' \
  --samples 20 \
  --warmup 1 \
  --output /tmp/parrot-agent-runtime-benchmark.json \
  --confirm-real-requests
```

脚本不记录回答正文，但会创建持久化 Interaction 并产生真实 Provider 费用，因此确认参数不可省略。每个样本使用
独立匿名会话，计时从发送 `interaction.create` 开始，不包含 WebSocket 建连。代码变更后必须先重启 TaskIQ
worker；只重载 Web 进程会继续执行旧 Runtime。当前本地基线和限制见
[Agent Runtime 性能基线](agent-runtime-performance-baseline.md)。

升级必须执行 migration `0054_mcp_tool_policies`。升级后，MCP Tool 默认没有自动执行授权；管理员需要先发现当前
Tool，再逐项保存 `effect` 和 `approval`。只有 `read + automatic` 进入自动路径，副作用 Tool 必须配置为
`approval=required`。保存时的 JSON Schema 与服务端 hash 是策略快照；远端 Schema 漂移会使执行失败闭合，管理员必须
重新发现并确认，不得直接修改 hash 绕过审核。

知识型与功能型 Root Agent 都可发现当前策略允许的远程 Tool；需要确认的 Tool 不再因 Agent 类型被隐藏。
Schedule、Subagent 等不能完成用户确认的入口仍只暴露自动查询 Tool，知识型仍不加载 stdio MCP。

Root WebSocket 的待审批 action 有效期为 15 分钟。approve/reject 提交后由 Web 进程直接投递 TaskIQ；scheduler 不
参与恢复。若 action 已进入 `executing` 但 worker 中断，运行时返回 `partial` 和“不确定、未重试”，值班人员应在目标
系统按业务幂等键或审计记录核对，不能重新点击审批。schedule、Child/Subagent 和非 Root 入口遇到需审批 Tool 会直接
拒绝，这是安全边界而不是故障。

Authorized administrators enter LLM, MCP, Embedding and reranker account credentials with the
corresponding resource. `embedding_configs` and `reranker_configs` are independent tenant-owned
tables; they do not extend `llm_configs` and each has a distinct AES-256-GCM authenticated context.
Management APIs return configured state without returning plaintext or ciphertext. The external
secrets TOML supplies the independent `security.credential_encryption_key`, which must be backed up
separately from the database. Never rotate or remove the old key until all stored envelopes have been
re-encrypted. Events, logs, browser storage, environment-variable fallbacks, and Skill sandboxes must
not receive credential values.

Migration `0024_database_credentials` cannot recover credential values from legacy reference names.
Before upgrading, inventory the affected LLM and MCP resources and retain the actual values through
an approved secret-handling channel. After upgrade, re-enter each value through the management UI/API
before enabling the resource. Do not copy plaintext into migration SQL or deployment logs.

Only the vector-store token remains a deployment secret reference. Knowledge Embedding and reranker
provider credentials are tenant configuration credentials. Memory and Knowledge continue to use
different vector credentials and collections even when the same infrastructure provider is selected.

The currently supported independent reranker is Alibaba Cloud Model Studio `qwen3-rerank`, following
the current [official rerank API](https://help.aliyun.com/zh/model-studio/text-rerank-api). Enter the
workspace-scoped base URL in the form
`https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-api/v1` and a Model Studio API Key;
the catalog defaults the model but cannot default a tenant's Workspace ID. The adapter calls the
provider-owned `POST /reranks` extension. It is shown in the provider documentation with the OpenAI
SDK, but it is not an endpoint in OpenAI's official API and must not be exposed as a generic OpenAI
reranker. Use the draft connection test before saving. The probe and runtime call the same adapter
and expose only bounded redacted provider diagnostics. Volcengine VikingDB Knowledge is a separate
product from Ark and is outside the current provider catalog; Ark API Keys and `/api/v3` do not
declare an independent reranker capability.

This provider change is not credential-compatible with an earlier VikingDB reranker configuration.
Before deploying it to an environment where that draft integration was enabled, inventory
`reranker_configs` rows whose provider is `volcengine_ark`, create and connection-test a new Bailian
configuration, and rebind every referencing knowledge space. Do not rewrite encrypted credentials
or provider keys in migration SQL: an IAM AK/SK pair cannot be converted into a Model Studio API Key.
If any active reference cannot be rebound, postpone the cutover rather than letting retrieval fail at
runtime.

Knowledge vector indexing has no global feature switch. Before any knowledge space selects an
Embedding configuration, the deployment must supply the Milvus service, vector credential,
monitoring, retention/data-transfer review and tenant-isolation tests. Selecting an active
Embedding configuration makes that space use vector plus keyword retrieval; the vector worker then
processes its queued jobs. A missing vector runtime is rejected when a new vector space is created,
rather than silently downgrading that space to keyword-only retrieval. There is no global `hybrid`
switch and no `knowledge-evaluate` gate in this flow.

The management flow makes that selection in the dedicated knowledge-space creation page, before any
document is uploaded. The selected configuration is a tenant-owned index profile; the document page
only adjusts query-time parameters such as candidate Top K, score thresholds and reranking. The
knowledge space persists an immutable provider/model/endpoint/dimension/version snapshot, and both
vector and lexical modes are locked at creation. Changing model identity requires a new Embedding
configuration and a new knowledge space with re-imported documents; it is never a retrieval-settings
edit.

## Database and process startup

```bash
cd backend
./.venv/bin/parrot db-upgrade --config config/prod.toml
./.venv/bin/parrot sync-permissions --config config/prod.toml
./.venv/bin/parrot serve --config config/prod.toml
taskiq worker --workers 1 --max-async-tasks 16 --ack-type when_executed app.modules.taskiq_entrypoints:container_broker
taskiq scheduler --update-interval 1 --loop-interval 1 app.modules.taskiq_entrypoints:container_scheduler
```

Run the worker and scheduler under independent supervision. The scheduler is singleton and owns
business schedules plus delayed background delivery; real-time interaction delivery is consumed directly
by workers. Workers may scale after Redis Stream pending-message monitoring and PostgreSQL lease-loss alerting are in place.
The Web process must not start background runtime, schedule, or indexing loops. The TaskIQ CLI factory
selects the explicitly mounted `/etc/parrot/config.toml`; it does not read configuration from environment
variables. For local development use `app.modules.taskiq_entrypoints:local_broker` and
`app.modules.taskiq_entrypoints:local_scheduler`, or use `make backend-taskiq` to start both native
TaskIQ containers. Before switching an existing deployment, run `parrot taskiq-backfill --config ...`
once after the worker and scheduler are healthy; it submits only previously pending records and is not a
long-running consumer.

The knowledge ingester reads only canonical private objects after an authorized upload confirmation;
it uses tenant-scoped leases and never publishes a document version before extraction succeeds.
Each knowledge space stores a chunk separator, paragraph-first chunk size/overlap, and local text-processing defaults for future documents. The ingester snapshots those settings per version, preserves the original private object, and indexes only the processed version text; changing defaults never rewrites published evidence.
The ingester validates the immutable Embedding snapshot stored on the knowledge space, so credential
rotation can continue to use the same vector space but a model identity mismatch never indexes data.
The TaskIQ knowledge-index task consumes durable version operations and stores only opaque identifiers in a
server-derived collection per Embedding configuration. Every job/reference records the selected
Embedding configuration and index revision. Existing spaces migrate to lexical mode and legacy
queued jobs are retired; selecting a configuration after explicit authorization is what queues an
index for published versions. Version replacement queues deletion/upsert jobs, but delayed vector
cleanup never controls authorization: every ANN candidate is rechecked against current PostgreSQL
Agent bindings and content state before text is returned.
Current scope validates MIME/extension, byte signature, size, extraction output and page limits, but
does not include malware scanning by product decision. Treat this as an accepted deployment risk and
keep the object-storage bucket private; add a sandboxed malware scanner before accepting untrusted
external uploads at scale.

## Runtime behavior

- Agent configuration resolves only active tenant bindings. Skill 和 MCP 都是租户资源，只有管理员
  显式绑定到 Agent 的资源才可发现和执行。
- Skill/MCP capability retrieval uses the deployment-owned `capability_index`: in-process BM25 is
  always available, and a healthy configured Embedding/Milvus index contributes semantic candidates
  that are fused with BM25 by RRF. Unlike the PostgreSQL knowledge lexical implementation, this
  capability lexical ranker is a strict BM25 implementation. The Skill management recall test uses
  the same ranker and Agent-bound Skill eligibility but intentionally excludes MCP discovery and all
  load/execute behavior.
- `knowledge_search` executes each bound space's policy independently: PostgreSQL keyword full-text
  retrieval is always available; when the vector store and an Embedding profile are both configured,
  vector candidates are fused with keyword candidates and may then be reranked. A vector/reranker
  failure only falls back for that space and never broadens its scope. The space-level recall test
  reuses this ranking policy after its own management authorization check, while the Agent detail
  test additionally enforces Agent bindings; both expose safe method/configuration/degradation
  metadata. The current PostgreSQL implementation uses `tsvector` and `ts_rank_cd`; it is not a
  strict BM25 implementation.
- Selecting an Embedding profile on a knowledge space authorizes and identifies the model, but does
  not configure the deployment-owned vector store. Vector fusion requires both the global
  `knowledge.vector` runtime to be enabled with a resolvable credential reference and the space's
  durable index jobs to complete. A queued or running index job keeps the space index state pending.
- Production executable Skills run only in the configured Bubblewrap sandbox. `local`/测试配置可
  显式允许受控本地子进程以便联调，但该选项必须在生产配置中保持关闭；MCP endpoints and stdio use
  configured host, credential, timeout, and sandbox policy.
- `todo` persists a bounded interaction checklist as durable events. `time` uses the explicitly
  configured IANA timezone. `math` accepts only AST-whitelisted symbolic expressions. `script` is
  disabled by default; if enabled, it shares the Skill Bubblewrap policy, has no network access,
  and must never permit unsafe local execution in production.
- Tool results are redacted and bounded before entering the next model turn. Repeated or highly
  similar `capability_execute` calls are stopped by the configured guard. Only pure `time` and
  `math` calls can run concurrently; database, network, sandbox, and stateful tools stay serial.
- Transient model transport failures retry only within the interaction timeout and configured
  attempt limit. Invalid requests and provider response-contract errors do not retry. A configured
  output-token limit is passed to OpenAI-compatible providers.
- Tool-round, total-tool-call, or consecutive-tool-error exhaustion enters the same no-tool final
  renderer with `runtime_status=partial` and an explicit budget reason. A normal reply is a nonempty
  no-tool response only after the entire Agent stream ends; it becomes a private terminal candidate,
  not an immediate client stream. `ask_user(question)` is the only explicit waiting-input terminal
  call and is offered only to a resumable root WebSocket Agent loop. Knowledge intent analysis,
  schedules, and subagents cannot enter `waiting_user_input`. `final_response()` remains accepted
  only for legacy model turns. A candidate that lacks
  required capability observation, or an empty no-tool response, receives at most one private repair
  turn and then a safe `partial`, never `AI_RESPONSE_PROTOCOL_INVALID` merely for omitting that tool.
- Candidate delivery writes a private checkpoint before publishing: full content, original provider
  deltas, delivery mode, stable `output_id`, terminal status and expiry. If recovery finds a visible,
  incomplete candidate delivery, it emits `ai.output.reset` for the same `output_id` and replays the
  persisted deltas without calling the provider or repeating the Agent/tool loop. The legacy final
  renderer retains its re-render recovery path. A non-streaming future IM adapter must consume only
  the completed/partial terminal event rather than wait for the runtime to buffer or manually rechunk
  text.
- `waiting_user_input` completes only the current model turn. The owner may send `interaction.steer`
  over the existing WebSocket; Parrot persists that control event, clears the previous waiting worker
  lease, commits the resumable state, and directly publishes the same interaction to TaskIQ. The next
  worker reconstructs the original request plus the latest clarification before the next Planner call.
  A steering message sent while the worker is still running remains an ordered control event and does
  not create a duplicate TaskIQ delivery.
- The conversation ledger stores every root user/assistant message under a monotonic interaction
  sequence. Waiting questions and steering replies commit in the same transaction as their source
  event, so later history reconstruction preserves every clarification exchange and timestamp.
- Capability-routing failures (`TOOL_NOT_AVAILABLE`, missing capability/MCP capability, or MCP execution
  route failure) receive at most `ai.agent_max_control_plane_replans` Planner retries. The retry budget
  never relaxes the tool-call or consecutive-error budgets.
- TaskBoard delegation persists child interactions with a depth limit of one, exact source spans
  from the latest user request, dependency checks, and bounded parallelism/budget. The runtime
  creates each child with the parent Agent's persisted profile; child interactions carry the task
  kind, hints, output contract and budget, use a synthetic plan without a Planner model call, and
  cannot clarify or delegate again. When all child tasks are terminal, the dispatcher requeues the
  parent exactly once; the parent aggregates persisted results in a terminal-candidate turn.
- Conversation history stores root user and completed assistant messages under tenant, actor,
  Agent, and server-derived P2P conversation scope. The model receives only that P2P conversation
  and treats it as reference data.
- Memory records require confirmation for inferred writes. Semantic vector results are candidates
  only and are always rechecked against the relational visibility rule.
- Agent-created schedules require exact latest-user source evidence, are owned by the same actor
  and Agent, and cannot recursively create schedules from a scheduled execution. Create, update,
  and cancel commit PostgreSQL state before synchronizing the corresponding TaskIQ schedule; the
  one-off `taskiq-backfill` command is recovery for historical pending state, not the normal write path.

## Smoke checks

1. Verify a published Agent has a default active LLM and the required Skills/MCP bindings.
2. Create an enabled WebSocket channel with an exact allowed Origin, bind it to a published anonymous
   Agent, send `interaction.create`, reconnect to
   `WSS /api/v1/im/ws/{channel_key}` using `interaction.subscribe`, and verify durable-event replay has
   no duplicate sequence. With the scheduler stopped and a worker still healthy, verify the interaction
   enters `running`; real-time IM delivery must not wait for the scheduler.
3. Submit a second message from the same visitor and confirm only the server-derived P2P transcript is
   injected.
4. Create, confirm, search, replace, and archive memory; check stale versions return
   `MEMORY_VERSION_CONFLICT`.
5. Run `taskiq-backfill` twice; the second run must not create duplicate side effects because task
   handlers fence by resource version and operation state.
6. Exercise a bound executable Skill and MCP tool with normal inputs, then confirm blocked host,
   credential, or sandbox violations fail closed.
7. Delegate two child tasks and verify they retain the parent Agent profile, the last child requeues
   the parent only after terminal results are persisted, and the parent emits one final response.
8. Create and cancel a schedule from an explicit user request; verify its execution becomes an
   interaction with `entry_type=schedule`.
9. Stop a TaskIQ worker during execution, allow the lease to expire, restart a worker, and verify a
   single authoritative terminal event and audit trail; stale worker events must be fenced out.
10. Force a transient model failure, a tool budget exhaustion, an ordinary no-tool reply, and a
    capability lookup without a tool observation. Verify bounded retry, durable candidate replay,
    one private observation repair, and a safe `partial` without publishing the blocked draft.
11. Force a clarification, send `interaction.steer`, and verify a distinct second `output_id`, the
    original request plus the clarification are present in the resumed Planner context, and no stale
    output is appended to the earlier question.
12. Upload a replacement knowledge file and verify the current published version remains searchable
    until the new extraction succeeds; download both immutable source versions through the authorized
    API and confirm an ungranted user receives no resource disclosure.
13. For a vector rollout, create active tenant Embedding/reranker configurations, authorize one test
    knowledge space, and use that Agent's real `knowledge_search` test to verify the selected space,
    model configuration, score, fallback reason and zero cross-space results. Verify unrelated spaces
    remain lexical, a referenced configuration may be disabled but remains usable by its existing
    spaces, and a referenced configuration cannot be deleted.

## Recovery and rollback

- Disable the affected Agent publication or schedule before changing runtime configuration.
- Before deploying the migration that removes static Agent-to-Agent bindings, drain or cancel
  interactions in `waiting_subagents`. A persisted TaskBoard from the old model may name a target
  Agent; the new runtime intentionally resumes only with the parent Agent profile and must not
  retain that cross-Agent delegation contract.
- Keep interactions, events, conversation messages, index jobs, schedule executions, and audit rows
  for diagnosis; never delete them to conceal a failed rollout.
- If vector or embedding services are unavailable, relational memory and the interaction runtime
  remain available; indexing jobs record failure and may be retried after the dependency recovers.
- Do not restore or configure a Skyler adapter. Roll back by deploying the previous Parrot release
  and using normal immutable Alembic migration discipline.
