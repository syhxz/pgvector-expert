#!/usr/bin/env python3
"""
estimate_index_size.py - Estimate pgvector index memory requirements (pure calculation).

Calculates the expected storage size for pgvector vector data and indexes (HNSW/IVFFlat),
and recommends appropriate Aurora PostgreSQL instance types based on memory requirements.

SECURITY NOTE:
    This is a pure calculation script. No database connections, no API calls,
    no network access, no file system modifications. Safe to run anywhere.

Usage:
    python estimate_index_size.py --rows 10000000 --dimension 1536 --index-type hnsw
    python estimate_index_size.py --rows 5000000 --dimension 768 --index-type ivfflat --format json
    python estimate_index_size.py --rows 50000000 --dimension 1536 --index-type hnsw --m 32 --replicas 2

Formulas:
    Vector data size:   rows × (dimension × 4 bytes + 36 bytes overhead) × 1.25 bloat / 1024³
    HNSW index size:    rows × dimension × 4 bytes × 1.33 overhead / 1024³
    IVFFlat index size: rows × dimension × 4 bytes × 1.10 overhead / 1024³

Requirements:
    - Python 3.8+ (no external dependencies)

Author: pgvector-expert skill
"""

import argparse
import json
import math
import sys

# Aurora PostgreSQL r8g 系列实例规格 (memory in GiB)
R8G_INSTANCES = [
    {"type": "db.r8g.medium",    "vcpu": 1,   "memory_gib": 8},
    {"type": "db.r8g.large",     "vcpu": 2,   "memory_gib": 16},
    {"type": "db.r8g.xlarge",    "vcpu": 4,   "memory_gib": 32},
    {"type": "db.r8g.2xlarge",   "vcpu": 8,   "memory_gib": 64},
    {"type": "db.r8g.4xlarge",   "vcpu": 16,  "memory_gib": 128},
    {"type": "db.r8g.8xlarge",   "vcpu": 32,  "memory_gib": 256},
    {"type": "db.r8g.12xlarge",  "vcpu": 48,  "memory_gib": 384},
    {"type": "db.r8g.16xlarge",  "vcpu": 64,  "memory_gib": 512},
    {"type": "db.r8g.24xlarge",  "vcpu": 96,  "memory_gib": 768},
    {"type": "db.r8g.48xlarge",  "vcpu": 192, "memory_gib": 1536},
]

# 常量
BYTES_PER_FLOAT32 = 4
TUPLE_OVERHEAD_BYTES = 36  # PostgreSQL tuple header + pgvector metadata
TABLE_BLOAT_FACTOR = 1.25  # 表膨胀因子 (fill factor, dead tuples etc.)
HNSW_OVERHEAD_FACTOR = 1.33  # HNSW 图结构额外开销 (neighbor lists, metadata)
IVFFLAT_OVERHEAD_FACTOR = 1.10  # IVFFlat 聚类开销较小
BYTES_PER_GIB = 1024 ** 3
MEMORY_MULTIPLIER = 1.5  # 推荐实例内存 = 索引大小 × 1.5 (留余量给 shared_buffers + OS)


def estimate_sizes(rows: int, dimension: int, index_type: str, m: int = 16) -> dict:
    """
    Estimate vector data and index sizes.

    Args:
        rows: Number of vectors (rows)
        dimension: Vector dimension
        index_type: 'hnsw' or 'ivfflat'
        m: HNSW m parameter (connections per layer), affects index size slightly

    Returns:
        Dictionary with size estimates in GB.
    """
    # 向量数据大小 (含 tuple overhead 和 bloat)
    vector_data_bytes = rows * (dimension * BYTES_PER_FLOAT32 + TUPLE_OVERHEAD_BYTES) * TABLE_BLOAT_FACTOR
    vector_data_gib = vector_data_bytes / BYTES_PER_GIB

    # 索引大小
    if index_type == "hnsw":
        # HNSW: 每个向量存储在图中，加上 neighbor list (约 2*m 个连接)
        index_bytes = rows * dimension * BYTES_PER_FLOAT32 * HNSW_OVERHEAD_FACTOR
        # m 参数影响: 更大的 m 意味着更多 neighbor 指针
        m_adjustment = (m / 16.0) * 0.1 + 0.9  # m=16 → 1.0x, m=32 → 1.1x, m=64 → 1.3x
        index_bytes *= m_adjustment
    else:
        # IVFFlat: 向量副本 + 聚类 centroids
        index_bytes = rows * dimension * BYTES_PER_FLOAT32 * IVFFLAT_OVERHEAD_FACTOR

    index_gib = index_bytes / BYTES_PER_GIB
    total_gib = vector_data_gib + index_gib

    return {
        "vector_data_gib": round(vector_data_gib, 2),
        "index_gib": round(index_gib, 2),
        "total_gib": round(total_gib, 2),
    }


def recommend_instance(min_memory_gib: float, replicas: int = 0) -> dict:
    """
    Recommend Aurora PostgreSQL instance type based on memory requirements.

    Args:
        min_memory_gib: Minimum required memory for indexes
        replicas: Number of Aurora read replicas (each needs same memory)

    Returns:
        Recommendation dict with instance type and details.
    """
    # 找到满足内存需求的最小实例
    recommended = None
    for instance in R8G_INSTANCES:
        # shared_buffers 通常设为实例内存的 25-40%，加上 OS 缓存
        # 实例可用内存约为总内存的 75% (减去 OS overhead)
        available_for_pg = instance["memory_gib"] * 0.75
        if available_for_pg >= min_memory_gib:
            recommended = instance.copy()
            break

    if recommended is None:
        # 超出最大实例，建议分片或降维
        recommended = {
            "type": "EXCEEDS_MAX_INSTANCE",
            "vcpu": 0,
            "memory_gib": 0,
            "note": "Required memory exceeds largest available instance. "
                    "Consider: (1) reduce dimensions, (2) use halfvec (float16), "
                    "(3) partition data across multiple databases, (4) use IVFFlat instead of HNSW.",
        }
    else:
        recommended["note"] = (
            f"Minimum instance for index + working set. "
            f"For production with headroom, consider one size up."
        )

    # 副本成本说明
    total_instances = 1 + replicas
    recommended["replicas"] = replicas
    recommended["total_instances"] = total_instances

    return recommended


def format_table(result: dict) -> str:
    """Format results as human-readable table."""
    lines = []
    lines.append("=" * 60)
    lines.append("  pgvector Index Size Estimation")
    lines.append("=" * 60)
    lines.append("")

    inp = result["input"]
    lines.append(f"  Rows:           {inp['rows']:>15,}")
    lines.append(f"  Dimension:      {inp['dimension']:>15}")
    lines.append(f"  Index Type:     {inp['index_type']:>15}")
    if inp["index_type"] == "hnsw":
        lines.append(f"  HNSW m:         {inp['m']:>15}")
    lines.append(f"  Replicas:       {inp['replicas']:>15}")
    lines.append("")
    lines.append("-" * 60)
    lines.append("  Size Estimates:")
    lines.append("-" * 60)

    sizes = result["sizes"]
    lines.append(f"  Vector data:          {sizes['vector_data_gib']:>10.2f} GiB")
    lines.append(f"  Index:                {sizes['index_gib']:>10.2f} GiB")
    lines.append(f"  Total (single node):  {sizes['total_gib']:>10.2f} GiB")
    lines.append("")

    rec = result["recommendation"]
    lines.append("-" * 60)
    lines.append("  Instance Recommendation:")
    lines.append("-" * 60)
    lines.append(f"  Min memory needed:    {result['min_memory_gib']:>10.2f} GiB")
    lines.append(f"  Recommended instance: {rec['type']:>18}")
    if rec.get("memory_gib"):
        lines.append(f"  Instance memory:      {rec['memory_gib']:>10} GiB")
        lines.append(f"  Instance vCPU:        {rec['vcpu']:>10}")
    lines.append(f"  Note: {rec.get('note', '')}")
    lines.append("")
    lines.append("=" * 60)

    return "\n".join(lines)


def format_json(result: dict) -> str:
    """Format results as JSON for agent consumption."""
    return json.dumps(result, indent=2, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(
        description="Estimate pgvector index size and recommend Aurora instance type. (Pure calculation, no DB connection needed)",
        epilog="Example: python estimate_index_size.py --rows 10000000 --dimension 1536 --index-type hnsw",
    )
    parser.add_argument("--rows", "-n", type=int, required=True, help="Number of vectors (rows)")
    parser.add_argument("--dimension", "-d", type=int, required=True, help="Vector dimension (e.g., 768, 1536)")
    parser.add_argument(
        "--index-type", "-t",
        choices=["hnsw", "ivfflat"],
        required=True,
        help="Index type: hnsw or ivfflat",
    )
    parser.add_argument("--m", type=int, default=16, help="HNSW m parameter (default: 16)")
    parser.add_argument("--replicas", "-r", type=int, default=0, help="Number of Aurora read replicas (default: 0)")
    parser.add_argument(
        "--format", "-f",
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )

    args = parser.parse_args()

    # 参数验证
    if args.rows <= 0:
        print("ERROR: --rows must be a positive integer.", file=sys.stderr)
        sys.exit(1)
    if args.dimension <= 0 or args.dimension > 16000:
        print("ERROR: --dimension must be between 1 and 16000.", file=sys.stderr)
        sys.exit(1)
    if args.m < 2 or args.m > 100:
        print("ERROR: --m must be between 2 and 100.", file=sys.stderr)
        sys.exit(1)

    # 计算大小
    sizes = estimate_sizes(
        rows=args.rows,
        dimension=args.dimension,
        index_type=args.index_type,
        m=args.m,
    )

    # 推荐最小实例内存: index_size × 1.5 (确保索引能完整缓存)
    min_memory_gib = sizes["index_gib"] * MEMORY_MULTIPLIER

    # 推荐实例类型
    recommendation = recommend_instance(min_memory_gib, args.replicas)

    # 组装结果
    result = {
        "tool": "estimate_index_size",
        "input": {
            "rows": args.rows,
            "dimension": args.dimension,
            "index_type": args.index_type,
            "m": args.m if args.index_type == "hnsw" else None,
            "replicas": args.replicas,
        },
        "sizes": sizes,
        "min_memory_gib": round(min_memory_gib, 2),
        "recommendation": recommendation,
        "formulas": {
            "vector_data": "rows × (dim × 4 + 36) × 1.25 / 1024³",
            "hnsw_index": "rows × dim × 4 × 1.33 × m_adj / 1024³",
            "ivfflat_index": "rows × dim × 4 × 1.10 / 1024³",
            "min_memory": "index_size × 1.5",
        },
    }

    # 输出
    if args.format == "json":
        print(format_json(result))
    else:
        print(format_table(result))


if __name__ == "__main__":
    main()
