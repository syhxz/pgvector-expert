#!/usr/bin/env python3
"""
analyze_pgvector.py - Analyze pgvector index configuration and provide recommendations.

Connects to a PostgreSQL database with pgvector extension and performs comprehensive
analysis of vector indexes, configuration parameters, and generates optimization
recommendations.

SECURITY NOTE:
    This script is STRICTLY READ-ONLY. It only executes:
    - SELECT statements (pg_catalog, pg_stat, information_schema queries)
    - SHOW statements (configuration parameters)
    - No INSERT, UPDATE, DELETE, CREATE, ALTER, DROP, or any DDL/DML operations.
    Safe to run against production databases without risk of data modification.

Usage:
    python analyze_pgvector.py --host mydb.cluster-xxx.us-east-1.rds.amazonaws.com \\
        --dbname myapp --user readonly_user --password '***' --action all
    python analyze_pgvector.py --host localhost --dbname dev --user postgres \\
        --action recommendations --format json

Actions:
    overview         - Database and pgvector configuration overview
    index-detail     - Detailed vector index information
    recommendations  - Automated optimization recommendations
    all              - All of the above

Requirements:
    - psycopg2 or psycopg (PostgreSQL adapter)
    - Target database must have pgvector extension installed

Author: pgvector-expert skill
"""

import argparse
import json
import sys
from typing import Any

try:
    import psycopg2
    import psycopg2.extras
    DB_ADAPTER = "psycopg2"
except ImportError:
    try:
        import psycopg
        DB_ADAPTER = "psycopg"
    except ImportError:
        print(
            "ERROR: psycopg2 or psycopg is required.\n"
            "Install with: pip install psycopg2-binary  OR  pip install psycopg[binary]",
            file=sys.stderr,
        )
        sys.exit(1)


def get_connection(host: str, port: int, dbname: str, user: str, password: str):
    """Create a database connection using available adapter."""
    conn_params = {
        "host": host,
        "port": port,
        "dbname": dbname,
        "user": user,
        "password": password,
    }
    try:
        if DB_ADAPTER == "psycopg2":
            conn = psycopg2.connect(**conn_params)
            conn.set_session(readonly=True, autocommit=True)
        else:
            conn = psycopg.connect(**conn_params, autocommit=True)
            conn.execute("SET default_transaction_read_only = on")
        return conn
    except Exception as e:
        print(f"ERROR: Failed to connect to database: {e}", file=sys.stderr)
        sys.exit(1)


def execute_query(conn, query: str, params=None) -> list[dict]:
    """Execute a read-only query and return results as list of dicts."""
    try:
        if DB_ADAPTER == "psycopg2":
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(query, params)
                if cur.description:
                    return [dict(row) for row in cur.fetchall()]
                return []
        else:
            with conn.cursor() as cur:
                cur.execute(query, params)
                if cur.description:
                    columns = [desc[0] for desc in cur.description]
                    return [dict(zip(columns, row)) for row in cur.fetchall()]
                return []
    except Exception as e:
        return [{"error": str(e)}]


def execute_scalar(conn, query: str, params=None) -> Any:
    """Execute a query and return single scalar value."""
    try:
        if DB_ADAPTER == "psycopg2":
            with conn.cursor() as cur:
                cur.execute(query, params)
                row = cur.fetchone()
                return row[0] if row else None
        else:
            with conn.cursor() as cur:
                cur.execute(query, params)
                row = cur.fetchone()
                return row[0] if row else None
    except Exception:
        return None


# =============================================================================
# Action: overview - 数据库和 pgvector 配置概览
# =============================================================================

def action_overview(conn) -> dict:
    """Gather database and pgvector configuration overview."""
    result = {}

    # PostgreSQL 版本
    result["pg_version"] = execute_scalar(conn, "SHOW server_version")
    result["pg_version_num"] = execute_scalar(conn, "SHOW server_version_num")

    # pgvector 版本
    pgvector_ver = execute_scalar(
        conn,
        "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
    )
    result["pgvector_version"] = pgvector_ver if pgvector_ver else "NOT INSTALLED"

    # 关键配置参数
    config_params = [
        "shared_buffers",
        "effective_cache_size",
        "maintenance_work_mem",
        "work_mem",
        "max_parallel_maintenance_workers",
        "max_parallel_workers_per_gather",
        "max_parallel_workers",
        "max_connections",
        "random_page_cost",
    ]
    result["configuration"] = {}
    for param in config_params:
        val = execute_scalar(conn, f"SHOW {param}")
        result["configuration"][param] = val

    # pgvector 相关 GUC 参数 (如果存在)
    vector_params = [
        "hnsw.ef_search",
        "ivfflat.probes",
    ]
    result["pgvector_settings"] = {}
    for param in vector_params:
        try:
            val = execute_scalar(conn, f"SHOW \"{param}\"")
            result["pgvector_settings"][param] = val
        except Exception:
            result["pgvector_settings"][param] = "default (not set)"

    # 数据库大小
    result["database_size"] = execute_scalar(
        conn, "SELECT pg_size_pretty(pg_database_size(current_database()))"
    )

    # 连接统计
    conn_stats = execute_query(
        conn,
        """
        SELECT count(*) as total_connections,
               count(*) FILTER (WHERE state = 'active') as active,
               count(*) FILTER (WHERE state = 'idle') as idle,
               count(*) FILTER (WHERE state = 'idle in transaction') as idle_in_transaction
        FROM pg_stat_activity
        WHERE datname = current_database()
        """
    )
    if conn_stats and "error" not in conn_stats[0]:
        result["connections"] = conn_stats[0]

    return result


# =============================================================================
# Action: index-detail - 向量索引详细信息
# =============================================================================

def action_index_detail(conn) -> dict:
    """Discover and analyze all vector indexes."""
    result = {"vector_columns": [], "indexes": [], "table_stats": []}

    # 发现所有 vector/halfvec 类型的列
    vector_columns = execute_query(
        conn,
        """
        SELECT
            n.nspname as schema_name,
            c.relname as table_name,
            a.attname as column_name,
            format_type(a.atttypid, a.atttypmod) as data_type,
            pg_size_pretty(pg_relation_size(c.oid)) as table_size,
            c.reltuples::bigint as estimated_rows
        FROM pg_attribute a
        JOIN pg_class c ON a.attrelid = c.oid
        JOIN pg_namespace n ON c.relnamespace = n.oid
        JOIN pg_type t ON a.atttypid = t.oid
        WHERE t.typname IN ('vector', 'halfvec', 'sparsevec')
          AND a.attnum > 0
          AND NOT a.attisdropped
          AND n.nspname NOT IN ('pg_catalog', 'information_schema')
        ORDER BY n.nspname, c.relname, a.attnum
        """
    )
    result["vector_columns"] = vector_columns if vector_columns and "error" not in vector_columns[0] else []

    # 查找所有向量索引 (HNSW 和 IVFFlat)
    vector_indexes = execute_query(
        conn,
        """
        SELECT
            n.nspname as schema_name,
            idx.relname as index_name,
            tbl.relname as table_name,
            am.amname as index_type,
            pg_size_pretty(pg_relation_size(idx.oid)) as index_size,
            pg_relation_size(idx.oid) as index_size_bytes,
            pg_get_indexdef(idx.oid) as index_definition,
            tbl.reltuples::bigint as table_rows
        FROM pg_index i
        JOIN pg_class idx ON i.indexrelid = idx.oid
        JOIN pg_class tbl ON i.indrelid = tbl.oid
        JOIN pg_namespace n ON idx.relnamespace = n.oid
        JOIN pg_am am ON idx.relam = am.oid
        WHERE am.amname IN ('hnsw', 'ivfflat')
          AND n.nspname NOT IN ('pg_catalog', 'information_schema')
        ORDER BY pg_relation_size(idx.oid) DESC
        """
    )
    result["indexes"] = vector_indexes if vector_indexes and "error" not in vector_indexes[0] else []

    # 解析索引参数 (从 index_definition 中提取 m, ef_construction, lists)
    for idx in result["indexes"]:
        idx_def = idx.get("index_definition", "")
        idx["parameters"] = _parse_index_params(idx_def, idx.get("index_type", ""))

    # 表级统计 (缓存命中率, seq_scan vs idx_scan)
    table_stats = execute_query(
        conn,
        """
        SELECT
            schemaname,
            relname as table_name,
            seq_scan,
            idx_scan,
            CASE WHEN (seq_scan + idx_scan) > 0
                THEN round(100.0 * idx_scan / (seq_scan + idx_scan), 2)
                ELSE 0
            END as idx_scan_pct,
            n_live_tup as live_rows
        FROM pg_stat_user_tables
        WHERE relname IN (
            SELECT DISTINCT tbl.relname
            FROM pg_index i
            JOIN pg_class idx ON i.indexrelid = idx.oid
            JOIN pg_class tbl ON i.indrelid = tbl.oid
            JOIN pg_am am ON idx.relam = am.oid
            WHERE am.amname IN ('hnsw', 'ivfflat')
        )
        ORDER BY relname
        """
    )
    result["table_stats"] = table_stats if table_stats and "error" not in table_stats[0] else []

    # 索引缓存命中率
    cache_stats = execute_query(
        conn,
        """
        SELECT
            indexrelname as index_name,
            relname as table_name,
            idx_blks_read,
            idx_blks_hit,
            CASE WHEN (idx_blks_read + idx_blks_hit) > 0
                THEN round(100.0 * idx_blks_hit / (idx_blks_read + idx_blks_hit), 2)
                ELSE 0
            END as cache_hit_ratio
        FROM pg_statio_user_indexes
        WHERE indexrelname IN (
            SELECT idx.relname
            FROM pg_index i
            JOIN pg_class idx ON i.indexrelid = idx.oid
            JOIN pg_am am ON idx.relam = am.oid
            WHERE am.amname IN ('hnsw', 'ivfflat')
        )
        ORDER BY cache_hit_ratio ASC
        """
    )
    result["index_cache_stats"] = cache_stats if cache_stats and "error" not in cache_stats[0] else []

    return result


def _parse_index_params(index_def: str, index_type: str) -> dict:
    """Parse index parameters from CREATE INDEX definition string."""
    params = {}
    idx_def_lower = index_def.lower()

    if index_type == "hnsw":
        # 提取 m 和 ef_construction
        if "m =" in idx_def_lower or "m=" in idx_def_lower:
            params["m"] = _extract_param_value(index_def, "m")
        else:
            params["m"] = 16  # default
        if "ef_construction" in idx_def_lower:
            params["ef_construction"] = _extract_param_value(index_def, "ef_construction")
        else:
            params["ef_construction"] = 64  # default

    elif index_type == "ivfflat":
        # 提取 lists
        if "lists" in idx_def_lower:
            params["lists"] = _extract_param_value(index_def, "lists")
        else:
            params["lists"] = 100  # default

    # 提取距离函数 (operator class)
    if "vector_l2_ops" in idx_def_lower:
        params["distance_function"] = "L2 (Euclidean)"
    elif "vector_ip_ops" in idx_def_lower:
        params["distance_function"] = "Inner Product"
    elif "vector_cosine_ops" in idx_def_lower:
        params["distance_function"] = "Cosine"
    else:
        params["distance_function"] = "unknown"

    return params


def _extract_param_value(definition: str, param_name: str) -> int:
    """Extract integer parameter value from index definition."""
    import re
    pattern = rf"{param_name}\s*=\s*(\d+)"
    match = re.search(pattern, definition, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return 0


# =============================================================================
# Action: recommendations - 自动化优化建议
# =============================================================================

def action_recommendations(conn, overview: dict = None, index_detail: dict = None) -> list[dict]:
    """Generate optimization recommendations based on analysis."""
    if overview is None:
        overview = action_overview(conn)
    if index_detail is None:
        index_detail = action_index_detail(conn)

    recommendations = []

    # --- 检查 pgvector 版本 ---
    pgvector_ver = overview.get("pgvector_version", "")
    if pgvector_ver and pgvector_ver != "NOT INSTALLED":
        ver_parts = pgvector_ver.split(".")
        try:
            major, minor = int(ver_parts[0]), int(ver_parts[1]) if len(ver_parts) > 1 else 0
            if major == 0 and minor < 7:
                recommendations.append({
                    "severity": "HIGH",
                    "category": "version",
                    "title": "pgvector version is outdated",
                    "detail": f"Current version: {pgvector_ver}. Recommend upgrading to 0.7.0+ "
                              f"for HNSW parallel build, halfvec support, and better performance.",
                    "action": "ALTER EXTENSION vector UPDATE;  -- then verify with SELECT extversion FROM pg_extension WHERE extname='vector'",
                })
            elif major == 0 and minor < 8:
                recommendations.append({
                    "severity": "MEDIUM",
                    "category": "version",
                    "title": "pgvector version could be newer",
                    "detail": f"Current version: {pgvector_ver}. Version 0.8.0+ includes "
                              f"improved HNSW build speed and sparsevec enhancements.",
                    "action": "Consider upgrading pgvector extension.",
                })
        except (ValueError, IndexError):
            pass
    elif pgvector_ver == "NOT INSTALLED":
        recommendations.append({
            "severity": "HIGH",
            "category": "version",
            "title": "pgvector extension not installed",
            "detail": "The pgvector extension is not installed in this database.",
            "action": "CREATE EXTENSION IF NOT EXISTS vector;",
        })

    # --- 检查 maintenance_work_mem ---
    maint_mem = overview.get("configuration", {}).get("maintenance_work_mem", "64MB")
    maint_mem_mb = _parse_memory_to_mb(maint_mem)
    if maint_mem_mb < 1024:
        recommendations.append({
            "severity": "MEDIUM",
            "category": "configuration",
            "title": "maintenance_work_mem is below 1GB",
            "detail": f"Current: {maint_mem} ({maint_mem_mb}MB). For large HNSW index builds, "
                      f"at least 1-2GB is recommended to avoid excessive disk I/O during index creation.",
            "action": "ALTER SYSTEM SET maintenance_work_mem = '2GB'; SELECT pg_reload_conf();",
        })

    # --- 检查 shared_buffers vs 索引大小 ---
    shared_buffers = overview.get("configuration", {}).get("shared_buffers", "128MB")
    shared_buffers_bytes = _parse_memory_to_bytes(shared_buffers)

    total_index_bytes = sum(
        idx.get("index_size_bytes", 0) for idx in index_detail.get("indexes", [])
    )
    if total_index_bytes > 0 and shared_buffers_bytes > 0:
        ratio = total_index_bytes / shared_buffers_bytes
        if ratio > 0.8:
            recommendations.append({
                "severity": "HIGH",
                "category": "memory",
                "title": "Vector indexes exceed 80% of shared_buffers",
                "detail": f"Total vector index size: {_bytes_to_pretty(total_index_bytes)}, "
                          f"shared_buffers: {shared_buffers}. Indexes may not fit in buffer cache, "
                          f"causing frequent disk reads and degraded query performance.",
                "action": "Increase shared_buffers or upgrade to a larger instance with more RAM. "
                          "Target: shared_buffers >= 1.5x total vector index size.",
            })
        elif ratio > 0.5:
            recommendations.append({
                "severity": "MEDIUM",
                "category": "memory",
                "title": "Vector indexes consuming significant portion of shared_buffers",
                "detail": f"Total vector index size: {_bytes_to_pretty(total_index_bytes)}, "
                          f"shared_buffers: {shared_buffers} (ratio: {ratio:.1%}).",
                "action": "Monitor cache hit ratio; consider increasing shared_buffers if performance degrades.",
            })

    # --- 检查 IVFFlat lists 参数 ---
    for idx in index_detail.get("indexes", []):
        if idx.get("index_type") == "ivfflat":
            lists = idx.get("parameters", {}).get("lists", 0)
            rows = idx.get("table_rows", 0)
            if rows > 0 and lists > 0:
                # 推荐: lists = rows/1000 (小表) 或 sqrt(rows) (大表)
                recommended_lists_small = max(1, rows // 1000)
                recommended_lists_sqrt = max(1, int(rows ** 0.5))
                recommended = recommended_lists_sqrt if rows > 1_000_000 else recommended_lists_small

                if lists < recommended * 0.5 or lists > recommended * 3:
                    recommendations.append({
                        "severity": "MEDIUM",
                        "category": "index_tuning",
                        "title": f"IVFFlat lists may be suboptimal for index '{idx.get('index_name')}'",
                        "detail": f"Current lists={lists}, table has ~{rows:,} rows. "
                                  f"Recommended: ~{recommended} (sqrt for large tables, rows/1000 for smaller).",
                        "action": f"Rebuild index with lists={recommended}: "
                                  f"REINDEX INDEX CONCURRENTLY {idx.get('index_name')};  "
                                  f"(after adjusting CREATE INDEX definition)",
                    })

    # --- 检查索引缓存命中率 ---
    for cache_stat in index_detail.get("index_cache_stats", []):
        hit_ratio = cache_stat.get("cache_hit_ratio", 100)
        if isinstance(hit_ratio, (int, float)) and hit_ratio < 90:
            recommendations.append({
                "severity": "HIGH" if hit_ratio < 70 else "MEDIUM",
                "category": "cache",
                "title": f"Low cache hit ratio for index '{cache_stat.get('index_name')}'",
                "detail": f"Cache hit ratio: {hit_ratio}%. Index reads are hitting disk frequently. "
                          f"This significantly impacts vector search latency.",
                "action": "Increase shared_buffers, upgrade instance memory, or consider "
                          "reducing index size (lower dimensions, use halfvec, or reduce m parameter).",
            })

    # --- 检查 seq_scan vs idx_scan ---
    for tbl_stat in index_detail.get("table_stats", []):
        seq_scan = tbl_stat.get("seq_scan", 0)
        idx_scan = tbl_stat.get("idx_scan", 0)
        if seq_scan > 0 and idx_scan > 0 and seq_scan > idx_scan * 2:
            recommendations.append({
                "severity": "MEDIUM",
                "category": "query_pattern",
                "title": f"High sequential scan ratio on table '{tbl_stat.get('table_name')}'",
                "detail": f"seq_scan={seq_scan:,}, idx_scan={idx_scan:,}. "
                          f"Many queries may not be using vector indexes effectively.",
                "action": "Review queries hitting this table. Ensure vector similarity searches "
                          "use proper ORDER BY with <->, <=>, or <#> operators and LIMIT clause. "
                          "Check that SET hnsw.ef_search and SET ivfflat.probes are configured.",
            })

    # --- 检查 hnsw.ef_search 设置 ---
    ef_search = overview.get("pgvector_settings", {}).get("hnsw.ef_search", "default (not set)")
    if ef_search == "default (not set)" or ef_search in ("40", "10"):
        has_hnsw = any(idx.get("index_type") == "hnsw" for idx in index_detail.get("indexes", []))
        if has_hnsw:
            recommendations.append({
                "severity": "LOW",
                "category": "configuration",
                "title": "hnsw.ef_search at default value",
                "detail": f"Current hnsw.ef_search={ef_search}. Default is 40. "
                          f"Higher values (100-200) improve recall at the cost of latency. "
                          f"Lower values (20-40) favor speed over accuracy.",
                "action": "SET hnsw.ef_search = 100;  -- adjust based on recall/latency tradeoff. "
                          "Benchmark with your workload to find optimal value.",
            })

    # --- 检查 max_parallel_maintenance_workers ---
    parallel_maint = overview.get("configuration", {}).get("max_parallel_maintenance_workers", "2")
    try:
        if int(parallel_maint) < 4:
            has_large_index = any(
                idx.get("index_size_bytes", 0) > 1_073_741_824  # > 1GB
                for idx in index_detail.get("indexes", [])
            )
            if has_large_index:
                recommendations.append({
                    "severity": "LOW",
                    "category": "configuration",
                    "title": "max_parallel_maintenance_workers may be too low for large indexes",
                    "detail": f"Current: {parallel_maint}. Large HNSW indexes benefit from "
                              f"parallel index builds (pgvector 0.7.0+).",
                    "action": "ALTER SYSTEM SET max_parallel_maintenance_workers = 7; SELECT pg_reload_conf();",
                })
    except ValueError:
        pass

    return recommendations


def _parse_memory_to_mb(value: str) -> int:
    """Parse PostgreSQL memory setting to megabytes."""
    value = value.strip().upper()
    try:
        if value.endswith("GB"):
            return int(float(value[:-2]) * 1024)
        elif value.endswith("MB"):
            return int(float(value[:-2]))
        elif value.endswith("KB"):
            return int(float(value[:-2]) / 1024)
        elif value.endswith("TB"):
            return int(float(value[:-2]) * 1024 * 1024)
        else:
            # 纯数字假定为 KB (PostgreSQL 默认)
            return int(int(value) * 8 / 1024)  # 8KB pages
    except (ValueError, TypeError):
        return 0


def _parse_memory_to_bytes(value: str) -> int:
    """Parse PostgreSQL memory setting to bytes."""
    return _parse_memory_to_mb(value) * 1024 * 1024


def _bytes_to_pretty(num_bytes: int) -> str:
    """Convert bytes to human-readable string."""
    if num_bytes >= 1024**3:
        return f"{num_bytes / 1024**3:.2f} GB"
    elif num_bytes >= 1024**2:
        return f"{num_bytes / 1024**2:.1f} MB"
    elif num_bytes >= 1024:
        return f"{num_bytes / 1024:.0f} KB"
    return f"{num_bytes} B"


# =============================================================================
# Output formatting
# =============================================================================

def format_output(data: dict, fmt: str) -> str:
    """Format the final output."""
    if fmt == "json":
        return json.dumps(data, indent=2, default=str, ensure_ascii=False)
    else:
        # pretty format - structured but readable
        return json.dumps(data, indent=2, default=str, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(
        description="Analyze pgvector index configuration and provide recommendations. (READ-ONLY)",
        epilog="Example: python analyze_pgvector.py --host mydb.rds.amazonaws.com "
               "--dbname app --user analyst --action all --format json",
    )
    parser.add_argument("--host", "-H", required=True, help="PostgreSQL host")
    parser.add_argument("--port", "-p", type=int, default=5432, help="PostgreSQL port (default: 5432)")
    parser.add_argument("--dbname", "-d", required=True, help="Database name")
    parser.add_argument("--user", "-U", required=True, help="Database user")
    parser.add_argument("--password", "-W", default="", help="Database password (or use PGPASSWORD env var)")
    parser.add_argument(
        "--action", "-a",
        choices=["overview", "index-detail", "recommendations", "all"],
        default="all",
        help="Analysis action to perform (default: all)",
    )
    parser.add_argument(
        "--format", "-f",
        choices=["json", "pretty"],
        default="json",
        help="Output format (default: json)",
    )

    args = parser.parse_args()

    # 如果未提供密码，尝试环境变量
    import os
    password = args.password or os.environ.get("PGPASSWORD", "")

    # 连接数据库
    conn = get_connection(args.host, args.port, args.dbname, args.user, password)

    try:
        output = {
            "tool": "analyze_pgvector",
            "host": args.host,
            "database": args.dbname,
            "action": args.action,
            "security": "READ-ONLY (SELECT/SHOW only)",
        }

        overview_data = None
        index_data = None

        if args.action in ("overview", "all"):
            overview_data = action_overview(conn)
            output["overview"] = overview_data

        if args.action in ("index-detail", "all"):
            index_data = action_index_detail(conn)
            output["index_detail"] = index_data

        if args.action in ("recommendations", "all"):
            # 确保有上下文数据用于生成建议
            if overview_data is None:
                overview_data = action_overview(conn)
            if index_data is None:
                index_data = action_index_detail(conn)
            recs = action_recommendations(conn, overview_data, index_data)
            output["recommendations"] = recs
            output["recommendation_count"] = len(recs)
            output["severity_summary"] = {
                "HIGH": sum(1 for r in recs if r["severity"] == "HIGH"),
                "MEDIUM": sum(1 for r in recs if r["severity"] == "MEDIUM"),
                "LOW": sum(1 for r in recs if r["severity"] == "LOW"),
            }

        print(format_output(output, args.format))

    finally:
        conn.close()


if __name__ == "__main__":
    main()
