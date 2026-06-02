---
name: pgvector-expert
display_name: pgvector 专家
description: "pgvector 向量数据库专家。激活场景：在 PostgreSQL 中使用 pgvector 做向量存储和检索、HNSW/IVFFlat 索引选型与调优、Aurora PostgreSQL + Bedrock Knowledge Base 构建 RAG 应用、向量搜索 SQL 代码生成、pgvector 性能优化、大规模写入/查询基准测试参考。适配 Quick Desktop、OpenClaw、Kiro、Claude Code。"
icon: "🐘"
trigger: pgvector
inputs:
  - name: task---
name: pgvector-expert
display_name: pgvector 专家
description: "pgvector 向量数据库专家。激活场景：在 PostgreSQL 中使用 pgvector 做向量存储和检索、HNSW/IVFFlat 索引选型与调优、Aurora PostgreSQL + Bedrock Knowledge Base 构建 RAG 应用、向量搜索 SQL 代码生成、pgvector 性能优化、大规模写入/查询基准测试参考。适配 Quick Desktop、OpenClaw、Kiro、Claude Code。"
icon: "🐘"
trigger: pgvector
inputs:
  - name: task
    description: "用户要完成的具体任务，如：建表、建索引、RAG 架构设计、性能调优、SQL 生成、迁移方案等"
    type: string
    required: true
  - name: dimension
    description: "向量维度。常见值：192（声纹）、256（轻量场景）、1024（Titan Embedding v2）、1536（OpenAI）、3072（text-embedding-3-large）"
    type: number
    default: 1024
  - name: database_type
    description: "PostgreSQL 部署方式：aurora（Aurora PostgreSQL）、rds（RDS PostgreSQL）、selfhosted（自建 PG）"
    type: string
    default: aurora
---

## Overview

pgvector 专家 skill 提供从安装到生产的全链路指导：pgvector 扩展配置、向量表设计、HNSW/IVFFlat 索引选型与参数调优、Amazon Bedrock Knowledge Base + Aurora PostgreSQL RAG 架构搭建、向量检索 SQL 代码生成、性能优化最佳实践，以及经过实测验证的大规模性能基准数据（4亿行/712GB）。

本 skill 以纯 Markdown 指令编写，兼容所有支持 SKILL.md 协议的 AI 编程工具（Amazon Quick Desktop、OpenClaw、Kiro、Claude Code）。

## Workflow

### Step 1: 理解任务类型
- **Mode**: `agentic`
- **Input**: `{{task}}`、`{{dimension}}`、`{{database_type}}`
- **Output**: 确定任务属于以下哪类：(A) 安装配置 (B) 表设计与 SQL 生成 (C) 索引选型与调优 (D) Bedrock KB RAG 架构 (E) 性能优化 (F) 混合检索（向量+全文）(G) 基准测试参考
- **Validate**: 任务类型清晰，可以路由到对应的 reference knowledge
- **On failure**: 向用户确认具体需求场景

### Step 2: 生成方案或代码
- **Mode**: `agentic`
- **Input**: 任务类型 + reference knowledge（见下文）
- **Output**: SQL 代码、架构方案、配置建议、或优化步骤
- **Validate**: SQL 语法正确，参数值在合理范围内
- **On failure**: 检查 pgvector 版本兼容性（Aurora PG 支持 v0.5.0+，最新 v0.8.2）

### Step 3: 输出与交付
- **Mode**: `agentic`
- **Input**: 生成的方案/代码
- **Output**: 格式化的代码块 + 解释 + 注意事项
- **Validate**: 包含必要的注释和参数说明
- **On failure**: 补充缺失的上下文说明

## Reference Knowledge

### 一、pgvector 安装与启用

```sql
-- 在 Aurora PostgreSQL / RDS PostgreSQL 中启用（无需编译）
CREATE EXTENSION vector;

-- 验证安装
SELECT * FROM pg_extension WHERE extname = 'vector';
```

**版本支持**：
- Aurora PostgreSQL：pgvector 预装，支持 PG 13+（最新 v0.8.0 on Aurora PG 17.7）
- RDS PostgreSQL：通过 shared_preload_libraries 配置
- 自建 PG：需从源码编译 `git clone --branch v0.8.2 https://github.com/pgvector/pgvector.git`

### 二、向量表设计

**基础表结构**：
```sql
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    embedding vector({{dimension}}),
    content TEXT,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);
```

**Bedrock Knowledge Base 标准表结构**：
```sql
CREATE SCHEMA IF NOT EXISTS bedrock_integration;
CREATE TABLE bedrock_integration.bedrock_kb (
    id UUID PRIMARY KEY,
    embedding vector({{dimension}}),
    chunks TEXT,
    metadata JSON,
    custom_metadata JSONB
);
```

**声纹/高写入场景表结构示例**（实测 4亿行）：
```sql
CREATE TABLE voice_info (
    embedding_id BIGINT PRIMARY KEY,
    embed vector(192),          -- 声纹向量，L2 归一化
    user_id BIGINT,
    speaker_uid BIGINT,
    device_id VARCHAR(128),
    meeting_id VARCHAR(128)
);
-- 业务过滤索引
CREATE INDEX idx_voice_info_user_id ON voice_info (user_id);
-- 向量索引（IVFFlat，写入优先）
CREATE INDEX idx_voice_info_embed ON voice_info USING ivfflat (embed vector_cosine_ops) WITH (lists = 100);
```

**支持的向量类型**：
| 类型 | 最大维度 | 场景 |
|------|---------|------|
| `vector` | 2,000 | 单精度浮点，通用场景 |
| `halfvec` | 4,000 | 半精度浮点，节省50%存储 |
| `bit` | 64,000 | 二进制向量，Hamming/Jaccard |
| `sparsevec` | 1,000 非零元素 | 稀疏向量 |

### 三、索引选型决策

#### 决策矩阵

| 场景 | 推荐索引 | 原因 |
|------|---------|------|
| **写入吞吐优先，查询要求相对不高** | IVFFlat | 构建快、写入时索引维护开销小 |
| **查询延迟优先** | HNSW | 速度-召回权衡更优，无需训练数据 |
| **大规模+高写入（亿级）** | IVFFlat | 实测4亿行写入仅下降12%，稳定43,848 rows/s |
| **中小规模+低延迟（< 1000万）** | HNSW | 空表可建索引，查询性能更优 |
| **需要频繁更新向量** | HNSW | 无需 REINDEX |

#### HNSW 索引
- **优势**: 查询性能更好（速度-召回权衡优于 IVFFlat）；无需训练数据，空表即可建索引；无需 REINDEX
- **劣势**: 构建速度慢，内存占用大，写入时索引维护开销较大
- **适用**: 查询延迟优先、数据量 < 1000万向量

```sql
-- 余弦距离（最常用）
CREATE INDEX ON documents USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
```

**HNSW 参数调优**：
| 参数 | 默认值 | 建议 | 影响 |
|------|--------|------|------|
| `m` | 16 | 16-64 | 每层最大连接数。增大→查询快、构建慢、内存大 |
| `ef_construction` | 64 | 64-256 | 构建时候选列表大小。增大→召回高、构建慢 |
| `hnsw.ef_search` | 40 | 40-200 | 查询时候选列表大小。增大→召回高、速度慢 |

```sql
SET hnsw.ef_search = 100;
```

#### IVFFlat 索引
- **优势**: 构建速度快，内存占用小，**写入时索引维护开销显著小于 HNSW**
- **劣势**: 需要先有数据（训练步骤）；需要定期 REINDEX；召回率相对低
- **适用**: 写入吞吐优先、大数据量、可接受略低召回率

```sql
-- lists 参数：行数 < 100万取 rows/1000，> 100万取 sqrt(rows)
CREATE INDEX ON documents USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
```

**IVFFlat 参数调优**：
| 参数 | 建议 | 影响 |
|------|------|------|
| `lists` | rows/1000 (< 1M) 或 sqrt(rows) (> 1M) | 桶数。增大→查询快、召回降 |
| `ivfflat.probes` | sqrt(lists) | 查询探测桶数。增大→召回高、速度慢 |

```sql
SET ivfflat.probes = 10;
```

### 四、距离函数

| 运算符 | 距离类型 | 索引 ops 类 | 适用场景 |
|--------|---------|-------------|---------|
| `<->` | L2 欧氏距离 | `vector_l2_ops` | 通用相似度 |
| `<#>` | 负内积 | `vector_ip_ops` | 归一化向量 |
| `<=>` | 余弦距离 | `vector_cosine_ops` | 文本/NLP 嵌入（最常用） |
| `<+>` | L1 曼哈顿距离 | `vector_l1_ops` | 特征差异 |
| `<~>` | Hamming 距离 | `bit_hamming_ops` | 二进制向量 |
| `<%>` | Jaccard 距离 | `bit_jaccard_ops` | 集合相似度 |

### 五、常用查询模式

```sql
-- 最近邻搜索（余弦相似度）
SELECT id, content, 1 - (embedding <=> $1) AS similarity
FROM documents
ORDER BY embedding <=> $1
LIMIT 10;

-- 带业务字段过滤的搜索（利用 btree + IVFFlat 组合）
SELECT embedding_id, 1 - (embed <=> $1::vector) AS similarity
FROM voice_info
WHERE user_id = $2
ORDER BY embed <=> $1::vector
LIMIT 10;

-- 距离阈值过滤
SELECT * FROM documents
WHERE embedding <=> $1 < 0.3
ORDER BY embedding <=> $1
LIMIT 20;

-- 混合检索：向量 + 全文（双路召回）
WITH vector_results AS (
    SELECT id, content, 1 - (embedding <=> $1) AS vec_score
    FROM documents ORDER BY embedding <=> $1 LIMIT 20
),
text_results AS (
    SELECT id, content, ts_rank(to_tsvector('simple', content), plainto_tsquery('simple', $2)) AS text_score
    FROM documents
    WHERE to_tsvector('simple', content) @@ plainto_tsquery('simple', $2)
    LIMIT 20
)
SELECT COALESCE(v.id, t.id) AS id,
       COALESCE(v.content, t.content) AS content,
       COALESCE(v.vec_score, 0) * 0.7 + COALESCE(t.text_score, 0) * 0.3 AS combined_score
FROM vector_results v FULL OUTER JOIN text_results t ON v.id = t.id
ORDER BY combined_score DESC LIMIT 10;
```

### 六、Bedrock Knowledge Base + Aurora pgvector RAG 架构

**架构流程**：
1. 数据源（S3）→ Bedrock KB 自动 split chunk + Embedding（Titan Text Embeddings v2）
2. 向量存储 → Aurora PostgreSQL pgvector
3. 查询时：用户问题 → Embedding → pgvector 向量检索 → 上下文增强 → LLM 生成回答

**完整配置**：
```sql
CREATE SCHEMA IF NOT EXISTS bedrock_integration;
CREATE TABLE bedrock_integration.bedrock_kb (
    id UUID PRIMARY KEY,
    embedding vector({{dimension}}),
    chunks TEXT,
    metadata JSON,---
name: pgvector-expert
display_name: pgvector 专家
description: "pgvector 向量数据库专家。激活场景：在 PostgreSQL 中使用 pgvector 做向量存储和检索、HNSW/IVFFlat 索引选型与调优、Aurora PostgreSQL + Bedrock Knowledge Base 构建 RAG 应用、向量搜索 SQL 代码生成、pgvector 性能优化、大规模写入/查询基准测试参考。适配 Quick Desktop、OpenClaw、Kiro、Claude Code。"
icon: "🐘"
trigger: pgvector
inputs:
  - name: task
    description: "用户要完成的具体任务，如：建表、建索引、RAG 架构设计、性能调优、SQL 生成、迁移方案等"
    type: string
    required: true
  - name: dimension
    description: "向量维度。常见值：192（声纹）、256（轻量场景）、1024（Titan Embedding v2）、1536（OpenAI）、3072（text-embedding-3-large）"
    type: number
    default: 1024
  - name: database_type
    description: "PostgreSQL 部署方式：aurora（Aurora PostgreSQL）、rds（RDS PostgreSQL）、selfhosted（自建 PG）"
    type: string
    default: aurora
---

## Overview

pgvector 专家 skill 提供从安装到生产的全链路指导：pgvector 扩展配置、向量表设计、HNSW/IVFFlat 索引选型与参数调优、Amazon Bedrock Knowledge Base + Aurora PostgreSQL RAG 架构搭建、向量检索 SQL 代码生成、性能优化最佳实践，以及经过实测验证的大规模性能基准数据（4亿行/712GB + HNSW 1000万行基准）。

本 skill 以纯 Markdown 指令编写，兼容所有支持 SKILL.md 协议的 AI 编程工具（Amazon Quick Desktop、OpenClaw、Kiro、Claude Code）。

## Workflow

### Step 1: 理解任务类型
- **Mode**: `agentic`
- **Input**: `{{task}}`、`{{dimension}}`、`{{database_type}}`
- **Output**: 确定任务属于以下哪类：(A) 安装配置 (B) 表设计与 SQL 生成 (C) 索引选型与调优 (D) Bedrock KB RAG 架构 (E) 性能优化 (F) 混合检索（向量+全文）(G) 基准测试参考
- **Validate**: 任务类型清晰，可以路由到对应的 reference knowledge
- **On failure**: 向用户确认具体需求场景

### Step 2: 生成方案或代码
- **Mode**: `agentic`
- **Input**: 任务类型 + reference knowledge（见下文）
- **Output**: SQL 代码、架构方案、配置建议、或优化步骤
- **Validate**: SQL 语法正确，参数值在合理范围内
- **On failure**: 检查 pgvector 版本兼容性（Aurora PG 支持 v0.5.0+，最新 v0.8.2）

### Step 3: 输出与交付
- **Mode**: `agentic`
- **Input**: 生成的方案/代码
- **Output**: 格式化的代码块 + 解释 + 注意事项
- **Validate**: 包含必要的注释和参数说明
- **On failure**: 补充缺失的上下文说明

## Reference Knowledge

### 一、pgvector 安装与启用

```sql
-- 在 Aurora PostgreSQL / RDS PostgreSQL 中启用（无需编译）
CREATE EXTENSION vector;

-- 验证安装
SELECT * FROM pg_extension WHERE extname = 'vector';
```

**版本支持**：
- Aurora PostgreSQL：pgvector 预装，支持 PG 13+（最新 v0.8.0 on Aurora PG 17.7）
- RDS PostgreSQL：通过 shared_preload_libraries 配置
- 自建 PG：需从源码编译 `git clone --branch v0.8.2 https://github.com/pgvector/pgvector.git`

### 二、向量表设计

**基础表结构**：
```sql
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    embedding vector({{dimension}}),
    content TEXT,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);
```

**Bedrock Knowledge Base 标准表结构**：
```sql
CREATE SCHEMA IF NOT EXISTS bedrock_integration;
CREATE TABLE bedrock_integration.bedrock_kb (
    id UUID PRIMARY KEY,
    embedding vector({{dimension}}),
    chunks TEXT,
    metadata JSON,
    custom_metadata JSONB
);
```

**声纹/高写入场景表结构示例**（实测 4亿行）：
```sql
CREATE TABLE voice_info (
    embedding_id BIGINT PRIMARY KEY,
    embed vector(192),
    user_id BIGINT,
    speaker_uid BIGINT,
    device_id VARCHAR(128),
    meeting_id VARCHAR(128)
);
CREATE INDEX idx_voice_info_user_id ON voice_info (user_id);
CREATE INDEX idx_voice_info_embed ON voice_info USING ivfflat (embed vector_cosine_ops) WITH (lists = 100);
```

**支持的向量类型**：
| 类型 | 最大维度 | 场景 |
|------|---------|------|
| `vector` | 2,000 | 单精度浮点，通用场景 |
| `halfvec` | 4,000 | 半精度浮点，节省50%存储 |
| `bit` | 64,000 | 二进制向量，Hamming/Jaccard |
| `sparsevec` | 1,000 非零元素 | 稀疏向量 |

### 三、索引选型决策

#### 决策矩阵

| 场景 | 推荐索引 | 原因 |
|------|---------|------|
| **写入吞吐优先** | IVFFlat | 构建快、写入时索引维护开销小 |
| **查询延迟优先** | HNSW | 速度-召回权衡更优，无需训练数据 |
| **大规模+高写入（亿级）** | IVFFlat | 实测4亿行写入仅下降12% |
| **中小规模+低延迟（< 1000万）** | HNSW | 空表可建索引，查询性能更优 |
| **需要频繁更新向量** | HNSW | 无需 REINDEX |

#### HNSW 索引
- **优势**: 查询性能更好；无需训练数据，空表即可建索引；无需 REINDEX
- **劣势**: 构建速度慢，内存占用大，写入时索引维护开销较大
- **适用**: 查询延迟优先、数据量 < 1000万向量

```sql
CREATE INDEX ON documents USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
```

**HNSW 参数调优**：
| 参数 | 默认值 | 建议 | 影响 |
|------|--------|------|------|
| `m` | 16 | 16-64 | 每层最大连接数。增大→查询快、构建慢、内存大 |
| `ef_construction` | 64 | 64-256 | 构建时候选列表大小。增大→召回高、构建慢 |
| `hnsw.ef_search` | 40 | 40-200 | 查询时候选列表大小。增大→召回高、速度慢 |

```sql
SET hnsw.ef_search = 100;
```

#### IVFFlat 索引
- **优势**: 构建速度快，内存占用小，**写入时索引维护开销显著小于 HNSW**
- **劣势**: 需要先有数据；需要定期 REINDEX；召回率相对低
- **适用**: 写入吞吐优先、大数据量、可接受略低召回率

```sql
CREATE INDEX ON documents USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
```

**IVFFlat 参数调优**：
| 参数 | 建议 | 影响 |
|------|------|------|
| `lists` | rows/1000 (< 1M) 或 sqrt(rows) (> 1M) | 桶数。增大→查询快、召回降 |
| `ivfflat.probes` | sqrt(lists) | 查询探测桶数。增大→召回高、速度慢 |

```sql
SET ivfflat.probes = 10;
```

### 四、距离函数

| 运算符 | 距离类型 | 索引 ops 类 | 适用场景 |
|--------|---------|-------------|---------|
| `<->` | L2 欧氏距离 | `vector_l2_ops` | 通用相似度 |
| `<#>` | 负内积 | `vector_ip_ops` | 归一化向量 |
| `<=>` | 余弦距离 | `vector_cosine_ops` | 文本/NLP 嵌入（最常用） |
| `<+>` | L1 曼哈顿距离 | `vector_l1_ops` | 特征差异 |
| `<~>` | Hamming 距离 | `bit_hamming_ops` | 二进制向量 |
| `<%>` | Jaccard 距离 | `bit_jaccard_ops` | 集合相似度 |

### 五、常用查询模式

```sql
-- 最近邻搜索（余弦相似度）
SELECT id, content, 1 - (embedding <=> $1) AS similarity
FROM documents
ORDER BY embedding <=> $1
LIMIT 10;

-- 带业务字段过滤的搜索
SELECT embedding_id, 1 - (embed <=> $1::vector) AS similarity
FROM voice_info
WHERE user_id = $2
ORDER BY embed <=> $1::vector
LIMIT 10;

-- 混合检索：向量 + 全文（双路召回）
WITH vector_results AS (
    SELECT id, content, 1 - (embedding <=> $1) AS vec_score
    FROM documents ORDER BY embedding <=> $1 LIMIT 20
),
text_results AS (
    SELECT id, content, ts_rank(to_tsvector('simple', content), plainto_tsquery('simple', $2)) AS text_score
    FROM documents
    WHERE to_tsvector('simple', content) @@ plainto_tsquery('simple', $2)
    LIMIT 20
)
SELECT COALESCE(v.id, t.id) AS id,
       COALESCE(v.content, t.content) AS content,
       COALESCE(v.vec_score, 0) * 0.7 + COALESCE(t.text_score, 0) * 0.3 AS combined_score
FROM vector_results v FULL OUTER JOIN text_results t ON v.id = t.id
ORDER BY combined_score DESC LIMIT 10;
```

### 六、Bedrock Knowledge Base + Aurora pgvector RAG 架构

**架构流程**：
1. 数据源（S3）→ Bedrock KB 自动 split chunk + Embedding（Titan Text Embeddings v2）
2. 向量存储 → Aurora PostgreSQL pgvector
3. 查询时：用户问题 → Embedding → pgvector 向量检索 → 上下文增强 → LLM 生成回答

**完整配置**：
```sql
CREATE SCHEMA IF NOT EXISTS bedrock_integration;
CREATE TABLE bedrock_integration.bedrock_kb (
    id UUID PRIMARY KEY,
    embedding vector({{dimension}}),
    chunks TEXT,
    metadata JSON,
    custom_metadata JSONB
);
CREATE INDEX ON bedrock_integration.bedrock_kb
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
CREATE INDEX ON bedrock_integration.bedrock_kb USING gin (to_tsvector('simple', chunks));
CREATE INDEX ON bedrock_integration.bedrock_kb USING gin (custom_metadata);
```

### 七、性能基准数据（实测验证）

#### A. IVFFlat 基准（4亿行 / 192维 / 712GB）

**测试环境**：Aurora PostgreSQL 17.7 | db.r8g.4xlarge (16 vCPU, 128 GB) | pgvector 0.8.0 | I/O-Optimized

**写入性能**（COPY FROM，16 并发，200行/批）：
| 指标 | 数值 |
|------|------|
| 平均写入速率 | 43,848 rows/s |
| 峰值写入速率 | 51,590 rows/s |
| 总写入耗时 | 2.5 小时（4 亿行） |
| 速率衰减 | 仅 12%（50K→44K rows/s） |

**查询性能**（user_id 过滤 + 向量 Top-10）：
| 并发数 | QPS | 平均延迟 |
|--------|-----|---------|
| 16 | **15,255** | **0.9 ms** |
| 128 | **29,250** | **3.9 ms** |

#### B. HNSW 基准（VectorDBBench，db.r8g.4xlarge，pgvector 0.8.0）

**测试环境**：Aurora PostgreSQL 17.4 | db.r8g.4xlarge | HNSW (m=16, ef_construction=200)

**索引构建时间**：
| 数据集 | 2 并发 | 8 并发 |
|--------|-------|-------|
| 768D / 1M | 1,313s | **228s**（5.7x 加速） |
| 768D / 10M | 25,388s | **7,639s** |
| 1536D / 5M | - | 5,219s |

**查询性能（100 并发）**：
| 数据集 | ef_search | QPS | Recall | P99 延迟 |
|--------|-----------|-----|--------|---------|
| 768D / 1M | 40 | **11,809** | 94.3% | 3.0ms |
| 768D / 1M | 60 | 8,878 | 96.3% | 3.3ms |
| 768D / 1M | 100 | 6,203 | 97.6% | 4.1ms |
| 768D / 10M | 40 | **10,088** | 91.3% | 3.7ms |
| 768D / 10M | 100 | 5,124 | 96.1% | 5.8ms |
| 1536D / 50K | 40 | **10,921** | 97.6% | 2.9ms |
| 1536D / 5M | 40 | **8,827** | 93.4% | 4.0ms |
| 1536D / 5M | 100 | 4,566 | 97.3% | 6.0ms |

**relaxed_order 优化**（`SET hnsw.iterative_scan = 'relaxed_order'`）：
- 768D/1M @100并发：11,809 → **12,693** QPS（+7.5%）
- 768D/10M @100并发：10,088 → **10,282** QPS（+1.9%）
- 召回率不变，延迟下降

**水平扩展（2 节点 + RDS Proxy）**：
| 节点数 | ef_search | 并发 | QPS | P99 延迟 |
|--------|-----------|------|-----|---------|
| 1 节点 | 40 | 100 | 12,693 | 2.8ms |
| **2 节点** | 40 | 100 | **20,964** | 3.7ms |
| **2 节点** | 40 | 200 | **23,521** | 4.2ms |

**HNSW 关键发现**：
- ef_search 40→100：QPS 下降 ~40%，召回率从 94% 提升至 97-99%
- 8 并发建索引比 2 并发快 **5.7 倍**（`max_parallel_maintenance_workers`）
- `relaxed_order` 提升 5-10% QPS，召回率不变
- 双节点 + RDS Proxy：QPS 线性扩展 ~90%
- 数据全缓存在内存中时缓存命中率 100%，无物理读

### 八、性能优化最佳实践

1. **索引构建优化**：
```sql
SET maintenance_work_mem = '2GB';
SET max_parallel_maintenance_workers = 7;
```

2. **量化加速**：
```sql
ALTER TABLE documents ALTER COLUMN embedding TYPE halfvec(1024);
CREATE INDEX ON documents USING hnsw ((embedding::halfvec(1024)) halfvec_cosine_ops);
```

3. **监控查询性能**：
```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM documents ORDER BY embedding <=> '[...]' LIMIT 10;
-- 确认使用了 Index Scan 而非 Seq Scan
```

4. **定期维护**（IVFFlat）：
```sql
REINDEX INDEX CONCURRENTLY documents_embedding_idx;
VACUUM ANALYZE documents;
```

## Lessons Learned

### Do
- 写入优先场景用 IVFFlat（索引维护开销显著小于 HNSW）
- 查询延迟优先用 HNSW
- 组合 btree（业务字段）+ 向量索引极大提升过滤查询性能（实测 0.9ms）
- 余弦距离 `<=>` 是 NLP/文本嵌入场景的默认选择
- 建索引前增大 `maintenance_work_mem`（至少 1GB，推荐 2GB）
- 增大 `max_parallel_maintenance_workers` 可将索引构建加速 5.7x
- 使用 `relaxed_order` 可免费提升 5-10% HNSW 查询 QPS
- 使用 Aurora I/O-Optimized 存储类型避免 IOPS 限制

### Don't
- 不要在没有数据时创建 IVFFlat 索引（需要训练数据）
- 不要将 `hnsw.ef_search` 设置过高（> 500 时延迟急剧增加）
- 不要忘记在 `<#>` 内积结果上乘以 -1（Postgres 返回负值）
- 不要在大数据量（亿级）下使用过小的 IVFFlat lists 值（推荐 sqrt(n)）
- 不要忽略 IVFFlat 的定期 REINDEX 需求（数据变化 > 20%）

### When to Ask the User
- 向量维度不确定时（取决于 Embedding 模型）
- 数据规模不明确时（影响索引类型和参数）
- 写入/查询优先级不明确时（决定 IVFFlat vs HNSW）
- 是否需要混合检索（取决于业务对准确率的要求）
- 是用新建 Aurora 实例还是复用现有实例
    custom_metadata JSONB
);
-- HNSW 索引（Bedrock KB 查询优先场景）
CREATE INDEX ON bedrock_integration.bedrock_kb
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
-- 全文检索索引（混合检索）
CREATE INDEX ON bedrock_integration.bedrock_kb USING gin (to_tsvector('simple', chunks));
-- JSONB 元数据索引（过滤）
CREATE INDEX ON bedrock_integration.bedrock_kb USING gin (custom_metadata);
```

**Embedding 模型选择**：
| 模型 | 维度 | 场景 |
|------|------|------|
| Titan Text Embeddings v2 | 256/512/1024 | AWS 原生，中英文 |
| Cohere Embed v3 | 1024 | 多语言，高质量 |
| 自定义模型 | 可变 | 特定领域微调 |

### 七、性能基准数据（实测验证）

**测试环境**：Aurora PostgreSQL 17.7 | db.r8g.4xlarge (16 vCPU, 128 GB RAM, Graviton4) | pgvector 0.8.0 | Aurora I/O-Optimized | IVFFlat (lists=100)

**数据规模**：4 亿行 | 192 维向量 | 表 381 GB + 索引 331 GB = 总 712 GB

#### 写入性能（COPY FROM，16 并发，200行/批）
| 指标 | 数值 |
|------|------|
| **平均写入速率** | 43,848 rows/s |
| **峰值写入速率** | 51,590 rows/s |
| **批次响应时间** | 37.3 ms |
| **总写入耗时** | 2.5 小时（4 亿行） |
| **速率衰减** | 仅 12%（50K→44K rows/s） |
| **CPU 均值/峰值** | 27% / 95%（峰值为索引维护突发） |

#### 查询性能（user_id 过滤 + 向量 Top-10，IVFFlat）
| 并发数 | QPS | 平均延迟 | 60秒总查询 |
|--------|-----|---------|-----------|
| 16 | **15,255** | **0.9 ms** | 916,020 |
| 128 | **29,250** | **3.9 ms** | 1,763,272 |

**关键发现**：
- 并发 16→128（8倍），QPS 提升 1.9 倍，延迟从 0.9ms 增至 3.9ms
- CPU 峰值 63.3%（128并发），仍有余量
- btree(user_id) + IVFFlat(embed) 组合过滤策略极为高效

#### 1000行/批写入延迟（4亿行已有数据上追加）
| 指标 | 数值 |
|------|------|
| 中位延迟 | 76.8 ms |
| 平均延迟 | 156.1 ms |
| P70 | < 77 ms |
| 最大延迟 | 296.6 ms（IVFFlat 索引维护毛刺） |

**如需严格 P99 < 200ms**：写入时临时禁用索引，或使用 `synchronous_commit = off`

### 八、性能优化最佳实践

1. **索引构建优化**：
```sql
SET maintenance_work_mem = '2GB';
SET max_parallel_maintenance_workers = 7;
```

2. **量化加速**（大规模场景）：
```sql
ALTER TABLE documents ALTER COLUMN embedding TYPE halfvec(1024);
CREATE INDEX ON documents USING hnsw ((embedding::halfvec(1024)) halfvec_cosine_ops);
```

3. **IVFFlat lists 参数校准**：
```sql
-- 4亿行：推荐 sqrt(400000000) ≈ 20000（当前 lists=100 偏小）
-- 增大 lists 可提升召回率，但增加索引构建时间
CREATE INDEX ON voice_info USING ivfflat (embed vector_cosine_ops) WITH (lists = 20000);
```

4. **监控查询性能**：
```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM documents ORDER BY embedding <=> '[...]' LIMIT 10;
-- 确认使用了 Index Scan (ivfflat/hnsw) 而非 Seq Scan
```

5. **定期维护**：
```sql
-- IVFFlat 需要定期重建（数据变化 > 20% 时）
REINDEX INDEX CONCURRENTLY documents_embedding_idx;
VACUUM ANALYZE documents;
```

## Output

根据 `{{task}}` 类型输出：
- **SQL 代码**：带注释的可直接执行的 SQL，包含参数建议和替代方案
- **架构方案**：流程图描述 + 配置步骤 + 最佳实践
- **性能预估**：基于基准数据的预期性能 + 优化建议
- **索引选型**：决策矩阵 + 参数推荐 + 权衡分析

## Lessons Learned

### Do
- 对写入吞吐优先、查询性能要求相对不高的场景，优先使用 IVFFlat 索引（写入索引维护开销显著小于 HNSW）
- 对查询延迟优先的场景，优先使用 HNSW 索引
- 组合使用 btree（业务字段）+ 向量索引可极大提升过滤查询性能（实测 0.9ms）
- 为 Bedrock KB 使用固定表结构（id/embedding/chunks/metadata/custom_metadata）
- 余弦距离 `<=>` 是 NLP/文本嵌入场景的默认选择
- 建索引前增大 `maintenance_work_mem`（至少 1GB，推荐 2GB）
- 使用 `SET LOCAL` 在事务内调整查询参数，避免影响其他会话
- 混合检索（向量 + GIN 全文）可显著提高召回准确率
- 使用 Aurora I/O-Optimized 存储类型避免 IOPS 限制

### Don't
- 不要在没有数据时创建 IVFFlat 索引（需要训练数据，否则效果极差）
- 不要将 `hnsw.ef_search` 设置过高（> 500 时延迟急剧增加）
- 不要忘记在 `<#>` 内积结果上乘以 -1（Postgres 返回负值）
- 不要对非归一化向量使用内积距离（用余弦距离替代）
- 不要在大数据量（亿级）下使用过小的 IVFFlat lists 值（4亿行用 lists=100 偏小，推荐 sqrt(n)）
- 不要忽略 IVFFlat 的定期 REINDEX 需求（数据变化 > 20%）

### Common Failures
- **索引未使用**：查询没有 `ORDER BY ... LIMIT`，或 LIMIT 过大 → 确保带 ORDER BY + LIMIT
- **召回率低**：HNSW `ef_search` 太小或 IVFFlat `probes` 太少 → 逐步增大并测试
- **维度不匹配**：插入向量维度与表定义不一致 → 确认 Embedding 模型输出维度
- **写入毛刺**：IVFFlat 索引维护 + Aurora 存储刷写导致偶发高延迟 → 考虑 synchronous_commit=off 或临时禁用索引
- **Bedrock KB Sync 失败**：Aurora PG 网络不可达 → 检查 VPC 安全组和子网配置

### When to Ask the User
- 向量维度不确定时（取决于选用的 Embedding 模型）
- 数据规模不明确时（影响索引类型和参数选择）
- 写入/查询优先级不明确时（决定 IVFFlat vs HNSW）
- 是否需要混合检索（取决于业务对准确率的要求）
- 是用新建 Aurora 实例还是复用现有实例
    description: "用户要完成的具体任务，如：建表、建索引、RAG 架构设计、性能调优、SQL 生成、迁移方案等"
    type: string
    required: true
  - name: dimension
    description: "向量维度。常见值：192（声纹）、256（轻量场景）、1024（Titan Embedding v2）、1536（OpenAI）、3072（text-embedding-3-large）"
    type: number
    default: 1024
  - name: database_type
    description: "PostgreSQL 部署方式：aurora（Aurora PostgreSQL）、rds（RDS PostgreSQL）、selfhosted（自建 PG）"
    type: string
    default: aurora
---

## Overview

pgvector 专家 skill 提供从安装到生产的全链路指导：pgvector 扩展配置、向量表设计、HNSW/IVFFlat 索引选型与参数调优、Amazon Bedrock Knowledge Base + Aurora PostgreSQL RAG 架构搭建、向量检索 SQL 代码生成、性能优化最佳实践，以及经过实测验证的大规模性能基准数据（4亿行/712GB）。

本 skill 以纯 Markdown 指令编写，兼容所有支持 SKILL.md 协议的 AI 编程工具（Amazon Quick Desktop、OpenClaw、Kiro、Claude Code）。

## Reference Knowledge

### 一、pgvector 安装与启用

```sql
CREATE EXTENSION vector;
SELECT * FROM pg_extension WHERE extname = 'vector';
```

**版本支持**：Aurora PostgreSQL 预装 pgvector（PG 13+，最新 v0.8.0 on Aurora PG 17.7）

### 二、索引选型决策矩阵

| 场景 | 推荐索引 | 原因 |
|------|---------|------|
| 写入吞吐优先，查询要求相对不高 | IVFFlat | 构建快、写入时索引维护开销小 |
| 查询延迟优先 | HNSW | 速度-召回权衡更优，无需训练数据 |
| 大规模+高写入（亿级） | IVFFlat | 实测4亿行写入仅下降12% |
| 中小规模+低延迟（<1000万） | HNSW | 空表可建索引，查询性能更优 |

### 三、HNSW 索引

```sql
CREATE INDEX ON documents USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
SET hnsw.ef_search = 100;
```

参数：m=16-64, ef_construction=64-256, ef_search=40-200

### 四、IVFFlat 索引

```sql
CREATE INDEX ON documents USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
SET ivfflat.probes = 10;
```

lists: rows/1000(<1M) 或 sqrt(rows)(>1M)

### 五、距离函数

| 运算符 | 类型 | ops 类 |
|--------|------|--------|
| `<->` | L2 | vector_l2_ops |
| `<=>` | 余弦 | vector_cosine_ops |
| `<#>` | 负内积 | vector_ip_ops |

### 六、Bedrock KB 表结构

```sql
CREATE SCHEMA IF NOT EXISTS bedrock_integration;
CREATE TABLE bedrock_integration.bedrock_kb (
    id UUID PRIMARY KEY,
    embedding vector(1024),
    chunks TEXT,
    metadata JSON,
    custom_metadata JSONB
);
```

### 七、性能基准（实测）

环境：Aurora PG 17.7 | db.r8g.4xlarge | pgvector 0.8.0 | 4亿行/712GB

**写入**：43,848 rows/s (16并发COPY)，衰减仅12%
**查询**：15,255 QPS@16并发(0.9ms) | 29,250 QPS@128并发(3.9ms)
**组合**：btree(user_id) + IVFFlat(embed) 过滤策略

### 八、性能优化

```sql
SET maintenance_work_mem = '2GB';
SET max_parallel_maintenance_workers = 7;
```

## Lessons Learned

### Do
- 写入优先场景用 IVFFlat（索引维护开销小于 HNSW）
- 查询优先场景用 HNSW
- 组合 btree + 向量索引提升过滤查询性能
- 建索引前增大 maintenance_work_mem（推荐2GB）
- 使用 Aurora I/O-Optimized 避免 IOPS 限制

### Don't
- 不要在没有数据时创建 IVFFlat 索引
- 不要将 hnsw.ef_search 设置 > 500
- 不要在亿级数据下使用过小的 lists 值
- 不要忽略 IVFFlat 的定期 REINDEX 需求
