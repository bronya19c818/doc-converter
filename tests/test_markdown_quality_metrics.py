from scripts.verify_markdown_scoring import summarize


def test_metrics_count_wrong_layer_false_heading_and_missed_repair():
    records = [
        {
            "role": "heading-1",
            "actual_role": "heading-1",
            "needs_repair": True,
            "repair_success": True,
            "changed": True,
        },
        {
            "role": "heading-2",
            "actual_role": "heading-3",
            "needs_repair": True,
            "repair_success": False,
            "changed": True,
        },
        {
            "role": "heading-2",
            "actual_role": "body-paragraph",
            "needs_repair": True,
            "repair_success": False,
            "changed": False,
        },
        {
            "role": "body-paragraph",
            "actual_role": "heading-1",
            "needs_repair": False,
            "repair_success": False,
            "changed": True,
        },
        {
            "role": "preserved",
            "actual_role": "heading-2",
            "needs_repair": False,
            "repair_success": False,
            "changed": True,
        },
    ]
    m = summarize(records)
    assert m["heading_precision"] == 0.5
    assert m["heading_recall"] == 2 / 3
    assert m["heading_layer_accuracy"] == 1 / 3
    assert m["correct_auto_repair_coverage"] == 1 / 3
    assert m["false_repairs"] == 3
    assert m["missed_repairs"] == 2
    assert m["true_list_errors"] == 1


def test_zero_required_repairs_is_not_reported_as_full_coverage():
    m = summarize(
        [
            {
                "role": "body-paragraph",
                "actual_role": "body-paragraph",
                "needs_repair": False,
                "repair_success": False,
                "changed": False,
            }
        ]
    )
    assert m["correct_auto_repair_coverage"] is None
