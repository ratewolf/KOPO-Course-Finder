"""실제 반환 값만 사용하는 로컬 결과 안내. 외부 API를 호출하지 않는다."""

import sqlglot
from sqlglot import exp


def result_message(result):
    if result.truncated:
        return f"결과가 많아 {len(result.rows)}행까지만 표시합니다. 전체 건수는 별도 집계하지 않았습니다."
    if not result.rows:
        return "조건에 맞는 강좌가 없습니다. 검색 조건을 확인해 주세요."
    if not result.aggregate:
        return f"조회 결과 {len(result.rows)}행입니다."
    tree = sqlglot.parse_one(result.sql, read="sqlite")
    if (
        len(result.rows) == 1
        and len(tree.expressions) == 1
        and not tree.args.get("group")
    ):
        column = tree.expressions[0]
        if isinstance(column, exp.Alias):
            column = column.this
        if isinstance(column, exp.Count):
            if isinstance(column.this, exp.Star):
                return f"강좌 수는 {result.rows[0][0]:,}개입니다."
            if (
                isinstance(column.this, exp.Distinct)
                and len(column.this.expressions) == 1
            ):
                item = column.this.expressions[0]
                if isinstance(item, exp.Column) and item.name == "subject_code":
                    return f"서로 다른 과목 수는 {result.rows[0][0]:,}개입니다."
    values = []
    for row in result.rows[:5]:
        values.append(
            ", ".join(f"{name}: {value}" for name, value in zip(result.columns, row))[
                :500
            ]
        )
    suffix = "\n나머지 집계 값은 표에서 확인해 주세요." if len(result.rows) > 5 else ""
    return f"집계 결과 {len(result.rows)}행입니다.\n" + "\n".join(values) + suffix
