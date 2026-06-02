#!/usr/bin/env python3
"""
get_aurora_pricing.py - Query Aurora PostgreSQL instance pricing via AWS Pricing API.

Retrieves on-demand pricing for Aurora PostgreSQL instances from the AWS Pricing API.
Supports filtering by region and instance type, with output in table or JSON format.

SECURITY NOTE:
    This script performs READ-ONLY API calls only (pricing:GetProducts).
    No write operations, no resource modifications, no data mutations.
    Safe to run in any environment without risk of side effects.

Usage:
    python get_aurora_pricing.py --region us-east-1
    python get_aurora_pricing.py --region us-west-2 --instance-type db.r8g.xlarge
    python get_aurora_pricing.py --region ap-northeast-1 --format json

Requirements:
    - boto3
    - AWS credentials with pricing:GetProducts permission
    - Pricing API is only available in us-east-1 and ap-south-1 endpoints

Author: pgvector-expert skill
"""

import argparse
import json
import sys
from typing import Any

try:
    import boto3
except ImportError:
    print("ERROR: boto3 is required. Install with: pip install boto3", file=sys.stderr)
    sys.exit(1)


# 定价 API 仅在 us-east-1 和 ap-south-1 可用
PRICING_API_REGION = "us-east-1"
HOURS_PER_MONTH = 730  # AWS 标准月小时数


def get_pricing_client():
    """Create a Pricing API client (always connects to us-east-1)."""
    return boto3.client("pricing", region_name=PRICING_API_REGION)


def query_aurora_pg_pricing(region: str, instance_type: str | None = None) -> list[dict[str, Any]]:
    """
    Query Aurora PostgreSQL on-demand instance pricing.

    Args:
        region: AWS region code (e.g., 'us-east-1')
        instance_type: Optional specific instance type filter (e.g., 'db.r8g.xlarge')

    Returns:
        List of pricing records with instance details.
    """
    client = get_pricing_client()

    # 构建过滤条件
    filters = [
        {"Type": "TERM_MATCH", "Field": "databaseEngine", "Value": "Aurora PostgreSQL"},
        {"Type": "TERM_MATCH", "Field": "regionCode", "Value": region},
        {"Type": "TERM_MATCH", "Field": "termType", "Value": "OnDemand"},
    ]

    if instance_type:
        filters.append(
            {"Type": "TERM_MATCH", "Field": "instanceType", "Value": instance_type}
        )

    results = []
    next_token = None

    while True:
        kwargs = {
            "ServiceCode": "AmazonRDS",
            "Filters": filters,
            "FormatVersion": "aws_v1",
            "MaxResults": 100,
        }
        if next_token:
            kwargs["NextToken"] = next_token

        try:
            response = client.get_products(**kwargs)
        except Exception as e:
            print(f"ERROR: Failed to query Pricing API: {e}", file=sys.stderr)
            sys.exit(1)

        for price_item_json in response.get("PriceList", []):
            price_item = json.loads(price_item_json) if isinstance(price_item_json, str) else price_item_json
            record = _parse_price_item(price_item)
            if record:
                results.append(record)

        next_token = response.get("NextToken")
        if not next_token:
            break

    # 按实例类型排序
    results.sort(key=lambda x: (x.get("memory_gib", 0), x.get("vcpu", 0)))
    return results


def _parse_price_item(item: dict) -> dict | None:
    """Parse a single pricing item into a structured record."""
    try:
        product = item.get("product", {})
        attributes = product.get("attributes", {})
        terms = item.get("terms", {})

        instance_type = attributes.get("instanceType", "")
        if not instance_type:
            return None

        vcpu = attributes.get("vcpu", "N/A")
        memory = attributes.get("memory", "N/A")
        # memory 格式通常为 "16 GiB"
        memory_gib = _parse_memory(memory)

        # 提取 On-Demand 价格
        price_per_hour = _extract_on_demand_price(terms)
        if price_per_hour is None:
            return None

        return {
            "instance_type": instance_type,
            "vcpu": int(vcpu) if vcpu != "N/A" else 0,
            "memory_gib": memory_gib,
            "price_per_hour_usd": round(price_per_hour, 4),
            "price_per_month_usd": round(price_per_hour * HOURS_PER_MONTH, 2),
        }
    except (KeyError, ValueError, TypeError):
        return None


def _parse_memory(memory_str: str) -> float:
    """Parse memory string like '16 GiB' to float."""
    try:
        parts = memory_str.replace(",", "").split()
        return float(parts[0])
    except (ValueError, IndexError):
        return 0.0


def _extract_on_demand_price(terms: dict) -> float | None:
    """Extract the on-demand hourly price from terms structure."""
    on_demand = terms.get("OnDemand", {})
    for _offer_key, offer in on_demand.items():
        price_dimensions = offer.get("priceDimensions", {})
        for _dim_key, dimension in price_dimensions.items():
            price_str = dimension.get("pricePerUnit", {}).get("USD", "0")
            price = float(price_str)
            if price > 0:
                return price
    return None


def format_table(results: list[dict]) -> str:
    """Format results as a human-readable table."""
    if not results:
        return "No pricing data found for the specified criteria."

    # 表头
    header = f"{'Instance Type':<22} {'vCPU':>5} {'Memory(GiB)':>11} {'$/Hour':>10} {'$/Month':>10}"
    separator = "-" * len(header)
    lines = [header, separator]

    for r in results:
        line = (
            f"{r['instance_type']:<22} "
            f"{r['vcpu']:>5} "
            f"{r['memory_gib']:>11.1f} "
            f"{r['price_per_hour_usd']:>10.4f} "
            f"{r['price_per_month_usd']:>10.2f}"
        )
        lines.append(line)

    lines.append(separator)
    lines.append(f"Total: {len(results)} instance type(s) found")
    return "\n".join(lines)


def format_json(results: list[dict], region: str) -> str:
    """Format results as JSON for agent consumption."""
    output = {
        "service": "Aurora PostgreSQL",
        "region": region,
        "pricing_type": "OnDemand",
        "currency": "USD",
        "hours_per_month": HOURS_PER_MONTH,
        "instance_count": len(results),
        "instances": results,
    }
    return json.dumps(output, indent=2, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(
        description="Query Aurora PostgreSQL on-demand instance pricing via AWS Pricing API.",
        epilog="Example: python get_aurora_pricing.py --region us-east-1 --format table",
    )
    parser.add_argument(
        "--region", "-r",
        required=True,
        help="AWS region code (e.g., us-east-1, ap-northeast-1)",
    )
    parser.add_argument(
        "--instance-type", "-i",
        default=None,
        help="Filter by specific instance type (e.g., db.r8g.xlarge)",
    )
    parser.add_argument(
        "--format", "-f",
        choices=["table", "json"],
        default="table",
        help="Output format: table (human-readable) or json (agent-parseable). Default: table",
    )

    args = parser.parse_args()

    # 查询定价
    results = query_aurora_pg_pricing(region=args.region, instance_type=args.instance_type)

    # 输出结果
    if args.format == "json":
        print(format_json(results, args.region))
    else:
        print(format_table(results))


if __name__ == "__main__":
    main()
