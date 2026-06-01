---
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
