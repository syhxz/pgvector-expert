# 🐘 pgvector-expert

> AI skill for pgvector vector database — from installation to production, with real-world benchmarks.

[![pgvector](https://img.shields.io/badge/pgvector-0.8.2-blue)](https://github.com/pgvector/pgvector)
[![Aurora PostgreSQL](https://img.shields.io/badge/Aurora_PostgreSQL-17.7-orange)](https://aws.amazon.com/rds/aurora/)
[![License](https://img.shields.io/badge/license-MIT-green)](#license)
[![Compatible](https://img.shields.io/badge/compatible-Quick_Desktop%20|%20OpenClaw%20|%20Kiro%20|%20Claude_Code-purple)](#compatibility)

---

## What is this?

A comprehensive SKILL.md for AI coding assistants that provides expert-level guidance on **pgvector** — the open-source vector similarity search extension for PostgreSQL. The skill covers everything from table design to production-scale performance tuning, backed by real benchmark data from **400 million rows / 712 GB** workloads.

## Features

The skill routes tasks to 11 specialized knowledge areas:

| Route | Description |
|-------|-------------|
| **(A)** Installation & Configuration | Extension setup, version compatibility |
| **(B)** Table Design & SQL Generation | Schema patterns, Bedrock KB tables, vector types |
| **(C)** Index Selection & Tuning | HNSW vs IVFFlat decision matrix, parameter tuning |
| **(D)** Bedrock KB RAG Architecture | End-to-end RAG with Aurora + Bedrock |
| **(E)** Performance Optimization | Build params, quantization, monitoring |
| **(F)** Hybrid Search | Vector + full-text dual-path retrieval |
| **(G)** Benchmark Reference | Production-tested performance data |
| **(H)** RAG Knowledge Base Best Practices | Chunking, retrieval enhancement, data quality |
| **(I)** Instance Selection & Optimized Reads | NVMe Tiered Cache, r8gd selection |
| **(J)** Framework Integration | LangChain, aws_ml extension |
| **(K)** Real-time Cluster Analysis | Live diagnostics & optimization suggestions |

## Quick Start

### Amazon Quick Desktop

The skill is automatically available when installed to your Quick Desktop profile:

```
~/.quickwork/profiles/<profile>/skills/pgvector-expert/SKILL.md
```

Just ask: *"Help me design a pgvector table for 10M embeddings with 1024 dimensions"*

### OpenClaw / Kiro / Claude Code

Place `SKILL.md` in your project's skill directory:

```bash
# OpenClaw (global)
~/.openclaw/skills/pgvector-expert/SKILL.md

# Kiro (project-scoped)
.kiro/skills/pgvector-expert/SKILL.md

# Claude Code (project)
.claude/skills/pgvector-expert/SKILL.md
```

The AI assistant will automatically load the skill when pgvector-related questions arise.

## Scripts

Three Python utility scripts for real-time diagnostics and planning:

### `scripts/estimate_storage_size.py`

Pure calculation — estimate storage and recommend instances. **No dependencies required.**

```bash
python3 scripts/estimate_storage_size.py \
  --rows 10000000 \
  --dimension 1024 \
  --index-type hnsw \
  --format table
```

Output:
```
================================================================
  pgvector Storage Size Estimation (Data + Index)
================================================================

  Rows:                  10,000,000
  Dimension:                   1024
  Index Type:                  hnsw

------------------------------------------------------------
  Size Estimates:
------------------------------------------------------------
  Vector data:               38.15 GiB
  Index:                     50.72 GiB
  Total (single node):       88.87 GiB

  Recommended instance:    db.r8g.4xlarge (128 GiB)
```

### `scripts/analyze_pgvector.py`

Connect to a live cluster and get optimization recommendations. **Read-only, never modifies data.**

```bash
python3 scripts/analyze_pgvector.py \
  --host aurora-cluster.xxx.rds.amazonaws.com \
  --dbname mydb --user admin --password *** \
  --action all \
  --format json
```

Analyzes: pgvector version, index types & parameters, cache hit ratios, and generates severity-ranked recommendations.

### `scripts/get_aurora_pricing.py`

Query real-time Aurora PostgreSQL instance pricing via AWS Pricing API.

```bash
python3 scripts/get_aurora_pricing.py \
  --region us-east-1 \
  --instance-type r8g.4xlarge \
  --format table
```

## Performance Benchmarks

### IVFFlat — 400M Rows Write + Query

| Metric | Result |
|--------|--------|
| Write rate (16 concurrency) | **43,848 rows/s** sustained |
| Write degradation over time | Only **12%** (50K → 44K) |
| Total 400M rows write time | **2.5 hours** |
| Query QPS (16 concurrency) | **15,255** @ 0.9ms avg |
| Query QPS (128 concurrency) | **29,250** @ 3.9ms avg |

*Environment: Aurora PG 17.7, db.r8g.4xlarge, 192D vectors, IVFFlat lists=100*

### HNSW — VectorDBBench

| Dataset | QPS @100 concurrency | Recall | P99 Latency |
|---------|---------------------|--------|-------------|
| 768D / 1M | **11,809** | 94.3% | 3.0ms |
| 768D / 10M | **10,088** | 91.3% | 3.7ms |
| 1536D / 5M | **8,827** | 93.4% | 4.0ms |

*Environment: Aurora PG 17.4, db.r8g.4xlarge, HNSW m=16 ef_construction=200*

**Key findings:**
- 8-worker parallel index build is **5.7x faster** than 2-worker
- `relaxed_order` mode: +5-10% QPS with no recall loss
- 2-node + RDS Proxy: QPS scales **~90% linearly**

## Compatibility

| Tool | Installation |
|------|-------------|
| **Amazon Quick Desktop** | `~/.quickwork/profiles/<profile>/skills/pgvector-expert/` |
| **OpenClaw** | Global steering or project `skills/` directory |
| **Kiro** | `.kiro/skills/pgvector-expert/` or agent skill resource |
| **Claude Code** | `.claude/skills/pgvector-expert/` |

The skill is written in pure Markdown following the SKILL.md protocol — no tool-specific dependencies.

## Repository Structure

```
pgvector-expert/
├── SKILL.md              # Main skill file (Chinese)
├── SKILL_EN.md           # English translation
├── README.md             # This file
└── scripts/
    ├── get_aurora_pricing.py      # AWS Pricing API query (boto3)
    ├── analyze_pgvector.py        # Live cluster analysis (psycopg2)
    └── estimate_storage_size.py   # Storage calculator (no deps)
```

## License

MIT

---

Built with real production data from Aurora PostgreSQL + pgvector workloads.
