"""Reproducible role/layer/coverage evaluation against pre-annotated source lines."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from doc_converter.normalizer import normalize_markdown

FIXTURES = Path(__file__).resolve().parents[1] / 'tests/fixtures/markdown_scoring'


def evaluate(fixtures: Path = FIXTURES) -> dict[str, Any]:
    truth = json.loads((fixtures / 'ground_truth.json').read_text(encoding='utf-8'))
    records: list[dict[str, Any]] = []
    for sample in truth['samples']:
        source = (fixtures / sample['file']).read_text(encoding='utf-8')
        result = normalize_markdown(source, filename=sample['file'])
        by_line = {d['line']: d for d in result.report['decisions']}
        for expected in sample['expected']:
            decision = by_line.get(expected['line'], {})
            role = decision.get('role', 'missing')
            records.append({
                'file': sample['file'], **expected, 'actual_role': role,
                'correct': role == expected['role'], 'action': decision.get('action', 'missing'),
                'score': decision.get('score'), 'margin': decision.get('margin'),
                'reason': decision.get('reason'),
            })
    headings = [r for r in records if r['role'].startswith('heading-')]
    actionable = [r for r in records if r['role'] != 'preserved']
    mapped = [r for r in actionable if r['action'] == 'mapped']
    return {
        'schema': 'markdown-quality/v1', 'scope': truth['scope'],
        'metrics': {
            'annotated_items': len(records),
            'correct_roles': sum(r['correct'] for r in records),
            'role_accuracy': sum(r['correct'] for r in records) / len(records),
            'heading_items': len(headings),
            'heading_layer_accuracy': sum(r['correct'] for r in headings) / len(headings),
            'auto_coverage': len(mapped) / len(actionable),
            'correct_auto_coverage': sum(r['correct'] for r in mapped) / len(actionable),
            'manual_corrections': sum(not r['correct'] for r in records),
        },
        'records': records,
        'limitations': ['按 Issue 层级口径标注的合成样本，不能替代真实业务文档总体统计。', '覆盖率与正确率分别计算；评分不是统计概率。'],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = evaluate()
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'quality.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report['metrics'], ensure_ascii=False, indent=2))
    # Quality results remain reviewable even below 100%; structural integrity
    # and exact regression contracts are enforced by the test suite.


if __name__ == '__main__':
    main()
