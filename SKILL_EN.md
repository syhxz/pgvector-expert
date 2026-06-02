---

name: pgvector-expert display_name: pgvector Expert description: "pgvector vector database expert. Activation scenarios: vector storage and retrieval with pgvector in PostgreSQL, HNSW/IVFFlat index selection and tuning, building RAG applications with Aurora PostgreSQL + Bedrock Knowledge Base, vector search SQL code generation, pgvector performance optimization, large-scale write/query benchmark references. Compatible with Quick Desktop, OpenClaw, Kiro, and Claude Code." icon: "🐘" trigger: pgvector inputs:

- name: task description: "The specific task to accomplish, e.g.: create table, create index, RAG architecture design, performance tuning, SQL generation, migration plan, etc." type: string required: true
- name: dimension description: "Vector dimension. Common values: 192 (voiceprint), 256 (lightweight), 1024 (Titan Embedding v2), 1536 (OpenAI), 3072 (text-embedding-3-large)" type: number default: 1024
- name: database_type description: "PostgreSQL deployment type: aurora (Aurora PostgreSQL), rds (RDS PostgreSQL), selfhosted (self-managed PG)" type: string default: aurora

---

## Overview

The pgvector expert skill provides end-to-end guidance from installation to production: pgvector extension configuration, vector table design, HNSW/IVFFlat index selection and parameter tuning, Amazon Bedrock Knowledge Base + Aurora PostgreSQL RAG architecture setup, vector search SQL code generation, performance optimization best practices, and production-validated large-scale performance benchmarks (400 million rows / 712 GB).

This skill is written in pure Markdown instructions, compatible with all AI coding tools that support the SKILL.md protocol (Amazon Quick Desktop, OpenClaw, Kiro, Claude Code).

## Workflow

### Step 1: Understand Task Type

- **Mode**: `agentic`
- **Input**: `{{task}}`, `{{dimension}}`, `{{database_type}}`
- **Output**: Determine which category the task belongs to: (A) Installation & Configuration (B) Table Design & SQL Generation (C) Index Selection & Tuning (D) Bedrock KB RAG Architecture (E) Performance Optimization (F) Hybrid Search (Vector + Full-text) (G) Benchmark Reference (H) RAG Knowledge Base Best Practices (I) Instance Selection & Optimized Reads (J) Framework Integration (LangChain/aws_ml) (K) Real-time Cluster Analysis & Diagnostics
- **Validate**: Task type is clear, can be routed to the corresponding reference knowledge
- **On failure**: Confirm with user the specific use case scenario

### Step 2: Generate Solution or Code

- **Mode**: `agentic`
- **Input**: Task type + reference knowledge (see below)
- **Output**: SQL code, architecture plan, configuration recommendations, or optimization steps
- **Validate**: SQL syntax is correct, parameter values are within reasonable range
- **On failure**: Check pgvector version compatibility (Aurora PG supports v0.5.0+, latest v0.8.2)

### Step 3: Output & Delivery

- **Mode**: `agentic`
- **Input**: Generated solution/code
- **Output**: Formatted code blocks + explanations + caveats
- **Validate**: Contains necessary comments and parameter descriptions
- **On failure**: Supplement missing contextual explanations

## Reference Knowledge

### 1. pgvector Installation & Setup

```sql
-- Enable on Aurora PostgreSQL / RDS PostgreSQL (no compilation needed)
CREATE EXTENSION vector;

-- Verify installation
SELECT * FROM pg_extension WHERE extname = 'vector';

```

**Version Support**:

- Aurora PostgreSQL: pgvector pre-installed, supports PG 13+ (latest v0.8.0 on Aurora PG 17.7)
- RDS PostgreSQL: Configure via shared_preload_libraries
- Self-hosted PG: Compile from source `git clone --branch v0.8.2 https://github.com/pgvector/pgvector.git`

### 2. Vector Table Design

**Basic Table Structure**:

```sql
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    embedding vector({{dimension}}),
    content TEXT,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);

```

**Bedrock Knowledge Base Standard Table Structure**:

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

**Voiceprint / High-Write Scenario Table Example** (tested with 400M rows):

```sql
CREATE TABLE voice_info (
    embedding_id BIGINT PRIMARY KEY,
    embed vector(192),          -- Voiceprint vector, L2 normalized
    user_id BIGINT,
    speaker_uid BIGINT,
    device_id VARCHAR(128),
    meeting_id VARCHAR(128)
);
-- Business filtering index
CREATE INDEX idx_voice_info_user_id ON voice_info (user_id);
-- Vector index (IVFFlat, write-priority)
CREATE INDEX idx_voice_info_embed ON voice_info USING ivfflat (embed vector_cosine_ops) WITH (lists = 100);

```

**Supported Vector Types**:

| Type | Max Dimensions | Use Case |
| --- | --- | --- |
| `vector` | 2,000 | Single-precision float, general purpose |
| `halfvec` | 4,000 | Half-precision float, 50% storage savings |
| `bit` | 64,000 | Binary vectors, Hamming/Jaccard |
| `sparsevec` | 1,000 non-zero elements | Sparse vectors |

### 3. Index Selection Decision

Decision Matrix

| Scenario | Recommended Index | Reason |
| --- | --- | --- |
| **Write throughput priority, moderate query requirements** | IVFFlat | Fast build, low index maintenance overhead on writes |
| **Query latency priority** | HNSW | Better speed-recall tradeoff, no training data needed |
| **Large-scale + high writes (100M+)** | IVFFlat | Tested: 400M rows with only 12% degradation, stable 43,848 rows/s |
| **Small-to-medium scale + low latency (< 10M)** | HNSW | Can index empty tables, better query performance |
| **Frequent vector updates needed** | HNSW | No REINDEX required |

HNSW Index

- **Advantages**: Better query performance (superior speed-recall tradeoff vs IVFFlat); no training data needed, can index empty tables; no REINDEX required
- **Disadvantages**: Slow build time, high memory usage, significant index maintenance overhead on writes
- **Best for**: Query latency priority, data volume < 10M vectors

```sql
-- Cosine distance (most common)
CREATE INDEX ON documents USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

```

**HNSW Parameter Tuning**:

| Parameter | Default | Recommended | Impact |
| --- | --- | --- | --- |
| `m` | 16 | 16-64 | Max connections per layer. Increase → faster queries, slower builds, more memory |
| `ef_construction` | 64 | 64-256 | Candidate list size during build. Increase → higher recall, slower builds |
| `hnsw.ef_search` | 40 | 40-200 | Candidate list size during query. Increase → higher recall, slower speed |

```sql
SET hnsw.ef_search = 100;

```

IVFFlat Index

- **Advantages**: Fast build, low memory usage, **significantly lower index maintenance overhead on writes than HNSW**
- **Disadvantages**: Requires existing data (training step); requires periodic REINDEX; relatively lower recall
- **Best for**: Write throughput priority, large data volumes, acceptable slightly lower recall

```sql
-- lists parameter: use rows/1000 for < 1M rows, sqrt(rows) for > 1M rows
CREATE INDEX ON documents USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

```

**IVFFlat Parameter Tuning**:

| Parameter | Recommended | Impact |
| --- | --- | --- |
| `lists` | rows/1000 (< 1M) or sqrt(rows) (> 1M) | Number of buckets. Increase → faster queries, lower recall |
| `ivfflat.probes` | sqrt(lists) | Number of buckets to probe at query time. Increase → higher recall, slower speed |

```sql
SET ivfflat.probes = 10;

```

### 4. Distance Functions

| Operator | Distance Type | Index Ops Class | Use Case |
| --- | --- | --- | --- |
| `<->` | L2 Euclidean | `vector_l2_ops` | General similarity |
| `<#>` | Negative inner product | `vector_ip_ops` | Normalized vectors |
| `<=>` | Cosine distance | `vector_cosine_ops` | Text/NLP embeddings (most common) |
| `<+>` | L1 Manhattan | `vector_l1_ops` | Feature differences |
| `<~>` | Hamming distance | `bit_hamming_ops` | Binary vectors |
| `<%>` | Jaccard distance | `bit_jaccard_ops` | Set similarity |

### 5. Common Query Patterns

```sql
-- Nearest neighbor search (cosine similarity)
SELECT id, content, 1 - (embedding <=> $1) AS similarity
FROM documents
ORDER BY embedding <=> $1
LIMIT 10;

-- Search with business field filtering (leveraging btree + IVFFlat combination)
SELECT embedding_id, 1 - (embed <=> $1::vector) AS similarity
FROM voice_info
WHERE user_id = $2
ORDER BY embed <=> $1::vector
LIMIT 10;

-- Distance threshold filtering
SELECT * FROM documents
WHERE embedding <=> $1 < 0.3
ORDER BY embedding <=> $1
LIMIT 20;

-- Hybrid search: vector + full-text (dual-path recall)
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

### 6. Bedrock Knowledge Base + Aurora pgvector RAG Architecture

**Architecture Flow**:

1. Data Source (S3) → Bedrock KB automatic split chunks + Embedding (Titan Text Embeddings v2)
2. Vector Storage → Aurora PostgreSQL pgvector
3. Query: User question → Embedding → pgvector vector search → Context augmentation → LLM response generation

**Complete Configuration**:

```sql
CREATE SCHEMA IF NOT EXISTS bedrock_integration;
CREATE TABLE bedrock_integration.bedrock_kb (
    id UUID PRIMARY KEY,
    embedding vector({{dimension}}),
    chunks TEXT,
    metadata JSON,
    custom_metadata JSONB
);
-- HNSW index (query-priority scenario for Bedrock KB)
CREATE INDEX ON bedrock_integration.bedrock_kb
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
-- Full-text search index (hybrid retrieval)
CREATE INDEX ON bedrock_integration.bedrock_kb USING gin (to_tsvector('simple', chunks));
-- JSONB metadata index (filtering)
CREATE INDEX ON bedrock_integration.bedrock_kb USING gin (custom_metadata);

```

**Embedding Model Selection**:

| Model | Dimensions | Use Case |
| --- | --- | --- |
| Titan Text Embeddings v2 | 256/512/1024 | AWS native, Chinese & English |
| Cohere Embed v3 | 1024 | Multilingual, high quality |
| Custom model | Variable | Domain-specific fine-tuning |

RAG Knowledge Base Best Practices

**Chunking Strategy (greatest impact on retrieval quality)**:

| Strategy | Chunk Size | Use Case |
| --- | --- | --- |
| Fixed length | 512-1024 tokens | General documents, quick implementation |
| Semantic segmentation | By paragraph/section | Structured docs (technical manuals, regulations) |
| Recursive splitting | First by heading, then paragraph | Long documents (whitepapers, reports) |
| Sliding window | 512 tokens + 20% overlap | Avoid context breakage |

- Titan Embedding v2 input limit is 8192 tokens; in practice **300-800 tokens** works best
- Preserve chunk context info (document title, section heading) as metadata
- 10-20% overlap prevents answers from being cut at chunk boundaries

**Enhanced Table Structure (RAG-specific)**:

```sql
CREATE TABLE knowledge_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    embedding vector({{dimension}}),
    content TEXT,                        -- Chunk text
    document_title TEXT,                 -- Source document title
    section_title TEXT,                  -- Parent section
    chunk_index INT,                     -- Chunk sequence within document (for context expansion)
    metadata JSONB,                      -- {"source": "s3://...", "author": "...", "date": "..."}
    access_level TEXT DEFAULT 'public',  -- Access control
    source_updated_at TIMESTAMPTZ,       -- Source document update time
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX ON knowledge_chunks USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 128);
CREATE INDEX ON knowledge_chunks USING gin (to_tsvector('simple', content));
CREATE INDEX ON knowledge_chunks USING gin (metadata);
CREATE INDEX ON knowledge_chunks (access_level);
CREATE INDEX ON knowledge_chunks (source_updated_at DESC);

```

**Retrieval Enhancement Strategies**:

```sql
-- Context window expansion: send preceding and following chunks together to LLM
WITH hit AS (
    SELECT id, document_title, chunk_index, content,
           1 - (embedding <=> $1) AS similarity
    FROM knowledge_chunks
    ORDER BY embedding <=> $1 LIMIT 5
)
SELECT kc.content, kc.chunk_index, hit.similarity
FROM hit
JOIN knowledge_chunks kc
  ON kc.document_title = hit.document_title
 AND kc.chunk_index BETWEEN hit.chunk_index - 1 AND hit.chunk_index + 1
ORDER BY hit.similarity DESC, kc.chunk_index;

-- Multi-path recall + deduplication
WITH semantic AS (
    SELECT id, content, 1 - (embedding <=> $1) AS score FROM knowledge_chunks
    ORDER BY embedding <=> $1 LIMIT 15
),
keyword AS (
    SELECT id, content, ts_rank(to_tsvector('simple', content), plainto_tsquery('simple', $2)) AS score
    FROM knowledge_chunks
    WHERE to_tsvector('simple', content) @@ plainto_tsquery('simple', $2) LIMIT 15
)
SELECT DISTINCT ON (id) * FROM (
    SELECT * FROM semantic UNION ALL SELECT * FROM keyword
) all_results ORDER BY id, score DESC;

```

**RAG Tuning Recommendations**:

| Dimension | Recommendation |
| --- | --- |
| ef_search | Set 100-200 (prefer over-recall, let LLM filter) |
| Top-K | Retrieve 15-20 first, Rerank then take 5-8 for LLM |
| Hybrid search | Strongly recommended (vector 70% + keyword 30%), huge improvement for proper nouns/codes |
| Deduplication | Hash content before insertion |
| Incremental updates | Replace by document_title + chunk_index, not full rebuild |
| Expiration cleanup | Periodically delete chunks with stale source_updated_at |
| Anomaly detection | Remove vectors with vector_norm(embedding) < 0.1 |

**Data Quality Maintenance**:

```sql
-- Detect anomalous vectors
SELECT id FROM knowledge_chunks
WHERE vector_norm(embedding) < 0.1;

-- Incremental update (replace by document)
DELETE FROM knowledge_chunks WHERE document_title = 'some_document.pdf';
-- Then re-insert new version chunks

```

### 7. Performance Benchmarks (Production-Validated)

**Test Environment**: Aurora PostgreSQL 17.7 | db.r8g.4xlarge (16 vCPU, 128 GB RAM, Graviton4) | pgvector 0.8.0 | Aurora I/O-Optimized | IVFFlat (lists=100)

**Data Scale**: 400 million rows | 192-dimension vectors | Table 381 GB + Index 331 GB = Total 712 GB

Write Performance (COPY FROM, 16 concurrency, 200 rows/batch)

| Metric | Value |
| --- | --- |
| **Average write rate** | 43,848 rows/s |
| **Peak write rate** | 51,590 rows/s |
| **Batch response time** | 37.3 ms |
| **Total write duration** | 2.5 hours (400M rows) |
| **Rate degradation** | Only 12% (50K→44K rows/s) |
| **CPU average/peak** | 27% / 95% (peak from index maintenance bursts) |

Query Performance (user_id filter + vector Top-10, IVFFlat)

| Concurrency | QPS | Avg Latency | 60s Total Queries |
| --- | --- | --- | --- |
| 16 | **15,255** | **0.9 ms** | 916,020 |
| 128 | **29,250** | **3.9 ms** | 1,763,272 |

**Key Findings**:

- Concurrency 16→128 (8x): QPS improves 1.9x, latency from 0.9ms to 3.9ms
- CPU peak 63.3% (at 128 concurrency), still has headroom
- btree(user_id) + IVFFlat(embed) combined filtering strategy is extremely efficient

1000-row/batch Write Latency (appending to existing 400M rows)

| Metric | Value |
| --- | --- |
| Median latency | 76.8 ms |
| Average latency | 156.1 ms |
| P70 | < 77 ms |
| Max latency | 296.6 ms (IVFFlat index maintenance spike) |

**For strict P99 < 200ms**: Temporarily disable index during writes, or use `synchronous_commit = off`

HNSW Index Size Calculation Methodology & Cost Estimation

**Aurora PostgreSQL Vector Storage Formula**:

```
Vector data size (GB) = rows × (dimension × 4 + 36) × 1.25 / (1024³)

Where actual size per row = vector storage (dim×4 + 8 bytes header) + PG row overhead (~28 bytes) + page overhead (5-15%)

HNSW index size (GB) = rows × dimension × 4 × 1.33 / (1024³)

Where 1.33 = (1 + M/4), the actual overhead factor when M=16

```

**Storage Reference for Different Dimensions (Aurora PostgreSQL)**:

| Dimension | 1M rows data | 1M rows index | Total (1M) | 10M rows total |
| --- | --- | --- | --- | --- |
| 384 | 1.5 GB | 1.9 GB | 3.4 GB | 34 GB |
| 768 | 2.9 GB | 3.8 GB | 6.7 GB | 67 GB |
| 1024 | 3.8 GB | 5.1 GB | 8.9 GB | 89 GB |
| 1536 | 5.7 GB | 7.6 GB | 13.3 GB | 133 GB |
| 2048 | 7.6 GB | 10.1 GB | 17.7 GB | 177 GB |

**Aurora PostgreSQL Cost Estimation Example** (768D, 1M rows, db.r8g.4xlarge ×2, us-east-1):

| Storage Type | Monthly Cost |
| --- | --- |
| I/O-Standard (including baseline + peak IO) | **$3,783/month** |
| I/O-Optimized (including storage $1.51) | **$4,487/month** |

**Storage & Cost Comparison Across Vector Stores** (768D, 1M rows):

| Vector Store | Data Size | Index Size | Total Storage | Monthly Cost | Notes |
| --- | --- | --- | --- | --- | --- |
| Aurora PostgreSQL | 2.9 GB | 3.8 GB | 6.7 GB | $3,783-$4,487 | 2×r8g.4xlarge |
| ElastiCache (Valkey 8.2) | 3.56 GB | 3.76 GB | 7.32 GB | $159.87 | r7g.large |
| MemoryDB (Valkey 7.3) | 3.59 GB | 0.45 GB | 4.04 GB | $255.50 | r7g.large |

**Key Insights**:

- ElastiCache stores complete vector copies in the index (4,033 bytes/row); MemoryDB stores only graph structure (479 bytes/row, **-88%**)
- Aurora PostgreSQL cost is mainly from compute instances ($3,224/month for 2×r8g.4xlarge), storage cost is very low
- For pure vector retrieval (no SQL requirements), ElastiCache/MemoryDB offers better cost-efficiency at small data volumes
- Aurora's advantages are SQL joins, transactions, multi-index combined filtering, unlimited storage scaling

**Capacity Planning Formula**:

```
Minimum instance memory ≥ HNSW index size × 1.5 (ensure index fully cached in memory)

Example: 768D/10M → Index 38GB → Recommend 64GB+ instance (e.g., db.r8g.2xlarge 64GB or 4xlarge 128GB)

```

HNSW Query Performance (VectorDBBench, db.r8g.4xlarge, pgvector 0.8.0)

**Test Environment**: Aurora PostgreSQL 17.4 | db.r8g.4xlarge | HNSW (m=16, ef_construction=200) | VectorDBBench

**Index Build Time**:

| Dataset | 2-worker build | 8-worker build |
| --- | --- | --- |
| 768D / 1M | 1,313s | **228s** (5.7x speedup) |
| 768D / 10M | 25,388s | **7,639s** |
| 1536D / 5M | - | 5,219s |

**Query Performance (100 concurrency)**:

| Dataset | ef_search | QPS | Recall | P99 Latency |
| --- | --- | --- | --- | --- |
| 768D / 1M | 40 | **11,809** | 94.3% | 3.0ms |
| 768D / 1M | 60 | 8,878 | 96.3% | 3.3ms |
| 768D / 1M | 80 | 7,385 | 97.1% | 3.7ms |
| 768D / 1M | 100 | 6,203 | 97.6% | 4.1ms |
| 768D / 10M | 40 | **10,088** | 91.3% | 3.7ms |
| 768D / 10M | 60 | 7,762 | 93.7% | 4.4ms |
| 768D / 10M | 100 | 5,124 | 96.1% | 5.8ms |
| 1536D / 50K | 40 | **10,921** | 97.6% | 2.9ms |
| 1536D / 50K | 100 | 5,875 | 99.5% | 4.3ms |
| 1536D / 5M | 40 | **8,827** | 93.4% | 4.0ms |
| 1536D / 5M | 100 | 4,566 | 97.3% | 6.0ms |

**relaxed_order Optimization** (`SET hnsw.iterative_scan = 'relaxed_order'`):

| Dataset | ef_search | QPS (standard) | QPS (relaxed) | Improvement |
| --- | --- | --- | --- | --- |
| 768D / 1M | 40 @100 concurrency | 11,809 | **12,693** | +7.5% |
| 768D / 10M | 40 @100 concurrency | 10,088 | **10,282** | +1.9% |

**Horizontal Scaling (2 nodes + RDS Proxy)**:

| Nodes | ef_search | Concurrency | QPS | Recall | P99 Latency |
| --- | --- | --- | --- | --- | --- |
| 1 node | 40 | 100 | 12,693 | 94.5% | 2.8ms |
| **2 nodes** | 40 | 100 | **20,964** | 94.5% | 3.7ms |
| **2 nodes** | 40 | 200 | **23,521** | 94.5% | 4.2ms |

**HNSW Key Findings**:

- ef_search 40→100: QPS drops ~40%, but recall improves from 94% to 97-99%
- Higher dimensions result in more significant QPS drop (768D > 1536D)
- 8-worker index build is **5.7x faster** than 2-worker (leveraging `max_parallel_maintenance_workers`)
- `relaxed_order` improves QPS by 5-10% with no recall loss
- Dual-node + RDS Proxy: QPS scales linearly ~90%, latency slightly increases due to Proxy
- 38GB data fully cached in 128GB memory, 100% cache hit rate, no physical reads

### 8. Performance Optimization Best Practices

1. **Index Build Optimization**:

```sql
SET maintenance_work_mem = '2GB';
SET max_parallel_maintenance_workers = 7;

```

1. **Quantization Acceleration** (large-scale scenarios):

```sql
ALTER TABLE documents ALTER COLUMN embedding TYPE halfvec(1024);
CREATE INDEX ON documents USING hnsw ((embedding::halfvec(1024)) halfvec_cosine_ops);

```

1. **IVFFlat lists Parameter Calibration**:

```sql
-- 400M rows: recommended sqrt(400000000) ≈ 20000 (current lists=100 is too small)
-- Increasing lists improves recall but increases index build time
CREATE INDEX ON voice_info USING ivfflat (embed vector_cosine_ops) WITH (lists = 20000);

```

1. **Monitor Query Performance**:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM documents ORDER BY embedding <=> '[...]' LIMIT 10;
-- Verify it uses Index Scan (ivfflat/hnsw) rather than Seq Scan

```

1. **Regular Maintenance**:

```sql
-- IVFFlat requires periodic rebuild (when data changes > 20%)
REINDEX INDEX CONCURRENTLY documents_embedding_idx;
VACUUM ANALYZE documents;

```

### 9. Aurora Optimized Reads & Instance Selection

**Optimized Reads Overview**:

- Uses local NVMe SSD as an extended cache layer beyond memory (Tiered Cache)
- When HNSW index exceeds shared_buffers, avoids direct reads from Aurora storage
- pgvector similarity search throughput improvement up to **9x**, query latency improvement up to **8x**
- Only available with I/O-Optimized storage mode

**Supported Instance Types**:

| Instance Family | Processor | NVMe Capacity | Available Versions |
| --- | --- | --- | --- |
| db.r8gd | Graviton4 | Up to 3.8TB | PG 17.4+ |
| db.r6gd | Graviton2 | Up to 1.9TB | PG 14.9+, 15.4+, 16.1+ |
| db.r6id | Intel | Up to 1.9TB | PG 14.9+, 15.4+, 16.1+ |

**Instance Selection Guidelines (pgvector scenarios)**:

| Scenario | Recommended Instance | Reason |
| --- | --- | --- |
| Index fits entirely in memory | db.r8g (no NVMe) | Best cost-efficiency, full memory cache hit |
| Index exceeds memory < 5x | db.r8gd (NVMe extension) | Tiered Cache avoids storage reads, controlled latency |
| Very large index + cost-sensitive | db.r8gd + read replicas | NVMe cache + horizontal scaling |

**r8gd vs r8g Performance Comparison** (Source: AWS Blog 2025-12):

- Upgrading from r6g to r8gd: throughput improvement **165%**, cost-efficiency improvement **120%**
- Application response time improvement **80%**
- Tiered Cache extends cache capacity to **5x** instance memory

**Activation**: No configuration needed; selecting r8gd/r6gd/r6id instance + I/O-Optimized automatically enables it

### 10. Framework Integration & aws_ml Extension

LangChain Integration

```python
# langchain-postgres (recommended, uses psycopg3)
from langchain_postgres import PGVector
from langchain_aws import BedrockEmbeddings

embeddings = BedrockEmbeddings(model_id="amazon.titan-embed-text-v2:0")

vectorstore = PGVector(
    embeddings=embeddings,
    collection_name="knowledge_base",
    connection="postgresql+psycopg://user:pass@aurora-endpoint:5432/dbname",
    use_jsonb=True,  # Recommended, supports metadata filtering
)

# Similarity search
docs = vectorstore.similarity_search("query text", k=10)

# Search with metadata filtering
docs = vectorstore.similarity_search(
    "query text", k=10, filter={"source": "technical-docs"}
)

```

**Note**: langchain-postgres uses psycopg3; connection string must use `postgresql+psycopg://` (not psycopg2)

aws_ml Extension (Call Bedrock directly from SQL)

```sql
-- Enable aws_ml extension
CREATE EXTENSION IF NOT EXISTS aws_ml CASCADE;

-- Generate Embeddings directly in SQL (no application-layer Bedrock API call needed)
SELECT aws_bedrock.invoke_model_get_embeddings(
    model_id := 'amazon.titan-embed-text-v2:0',
    content_type := 'application/json',
    accept_type := 'application/json',
    model_input := '{"inputText": "Text to generate vector for"}',
    output_json_path := '$.embedding'
) AS embedding;

-- Practical scenario: auto-generate embedding on insert
INSERT INTO documents (content, embedding)
SELECT 'New document content',
       aws_bedrock.invoke_model_get_embeddings(
           model_id := 'amazon.titan-embed-text-v2:0',
           content_type := 'application/json',
           accept_type := 'application/json',
           model_input := '{"inputText": "New document content"}',
           output_json_path := '$.embedding'
       )::vector(1024);

-- Real-time query vector generation (suitable for low-frequency queries; for high-frequency, cache at application layer)
SELECT id, content, 1 - (embedding <=> (
    aws_bedrock.invoke_model_get_embeddings(
        model_id := 'amazon.titan-embed-text-v2:0',
        content_type := 'application/json',
        accept_type := 'application/json',
        model_input := '{"inputText": "User question"}',
        output_json_path := '$.embedding'
    )::vector(1024)
)) AS similarity
FROM documents
ORDER BY embedding <=> (...)
LIMIT 10;

```

**aws_ml Prerequisites**: Aurora cluster must have IAM Role configured for Bedrock access, and cluster must be in the same Region as Bedrock

## Output

Based on `{{task}}` type, output:

- **SQL Code**: Annotated, directly executable SQL with parameter recommendations and alternatives
- **Architecture Plan**: Flow diagram description + configuration steps + best practices
- **Performance Estimate**: Expected performance based on benchmark data + optimization suggestions
- **Index Selection**: Decision matrix + parameter recommendations + tradeoff analysis

## Scripts

This skill includes 3 Python tool scripts that AI Agents can invoke via shell for real-time data:

### get_aurora_pricing.py

- **Purpose**: Query Aurora PostgreSQL instance real-time pricing (AWS Pricing API)
- **Usage**: `python3 scripts/get_aurora_pricing.py --region us-east-1 [--instance-type r8g.4xlarge] [--format json]`
- **Safety**: Read-only, queries only public pricing data
- **Dependencies**: boto3, AWS credentials
- **Output**: instance_type, vCPU, memory, $/hour, $/month

### analyze_pgvector.py

- **Purpose**: Connect to PostgreSQL cluster, analyze pgvector index configuration and generate optimization recommendations
- **Usage**: `python3 scripts/analyze_pgvector.py --host <endpoint> --dbname <db> --user <user> --password <pass> --action all --format json`
- **Safety**: Read-only, executes only SELECT/SHOW statements, never modifies data
- **Dependencies**: psycopg2-binary
- **Analysis Dimensions**:- Cluster overview (PG version, pgvector version, memory config, connections)
- Index details (auto-discovers vector/halfvec columns, index types & parameters, size, cache hit ratio)
- Optimization recommendations (index size vs memory, IVFFlat lists calibration, cache hit ratio, version check)

### estimate_storage_size.py

- **Purpose**: Pure calculation — estimate vector data + index storage size and recommend instance based on dimensions and row count
- **Usage**: `python3 scripts/estimate_storage_size.py --rows 5000000 --dimension 1024 --index-type hnsw [--format json]`
- **Safety**: Pure local calculation, no network access
- **Dependencies**: None (Python standard library)
- **Output**: Data size, index size, total, recommended memory, recommended instance type

## Lessons Learned

### Do

- For write-throughput-priority scenarios with moderate query performance requirements, prefer IVFFlat index (significantly lower write index maintenance overhead than HNSW)
- For query-latency-priority scenarios, prefer HNSW index
- Combine btree (business fields) + vector index to dramatically improve filtered query performance (tested at 0.9ms)
- Use the fixed table structure for Bedrock KB (id/embedding/chunks/metadata/custom_metadata)
- Cosine distance `<=>` is the default choice for NLP/text embedding scenarios
- Increase `maintenance_work_mem` before building indexes (at least 1GB, recommend 2GB)
- Use `SET LOCAL` to adjust query parameters within transactions to avoid affecting other sessions
- Hybrid search (vector + GIN full-text) significantly improves recall accuracy
- Use Aurora I/O-Optimized storage type to avoid IOPS limitations

### Don't

- Don't create IVFFlat indexes on empty tables (requires training data; results will be extremely poor)
- Don't set `hnsw.ef_search` too high (> 500 causes dramatic latency increase)
- Don't forget to multiply `<#>` inner product results by -1 (Postgres returns negative values)
- Don't use inner product distance on non-normalized vectors (use cosine distance instead)
- Don't use too-small IVFFlat lists values at large scale (400M rows with lists=100 is too small; recommend sqrt(n))
- Don't ignore IVFFlat's periodic REINDEX requirement (when data changes > 20%)

### Common Failures

- **Index not used**: Query lacks `ORDER BY ... LIMIT`, or LIMIT is too large → Ensure ORDER BY + LIMIT present
- **Low recall**: HNSW `ef_search` too small or IVFFlat `probes` too few → Incrementally increase and test
- **Dimension mismatch**: Inserted vector dimensions don't match table definition → Confirm Embedding model output dimensions
- **Write spikes**: IVFFlat index maintenance + Aurora storage flush causing occasional high latency → Consider synchronous_commit=off or temporarily disable index
- **Bedrock KB Sync failure**: Aurora PG network unreachable → Check VPC security group and subnet configuration

### When to Ask the User

- When vector dimension is uncertain (depends on chosen Embedding model)
- When data scale is unclear (affects index type and parameter selection)
- When write/query priority is unclear (determines IVFFlat vs HNSW)
- Whether hybrid search is needed (depends on business accuracy requirements)
- Whether to create a new Aurora instance or reuse an existing one

