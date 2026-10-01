"""Calculate deterministic differences between two experiments."""

from models.schemas import ExperimentComparison, ExperimentRun, MetricDelta, MetricSet


RATIO_METRICS = frozenset({"precision", "recall", "f1", "map50", "map50_95"})


def compare_experiments(
    baseline: ExperimentRun, current: ExperimentRun
) -> ExperimentComparison:
    """Compare shared metrics; relative change is undefined for a zero baseline."""

    if baseline.metric_scope != current.metric_scope:
        raise ValueError("不能比较不同指标口径的实验")
    if baseline.split != current.split:
        raise ValueError("不能比较不同 split 的实验")

    deltas: dict[str, MetricDelta] = {}
    for metric_name in MetricSet.model_fields:
        baseline_value = getattr(baseline.metrics, metric_name)
        current_value = getattr(current.metrics, metric_name)
        if baseline_value is None or current_value is None:
            continue
        difference = current_value - baseline_value
        deltas[metric_name] = MetricDelta(
            baseline_value=baseline_value,
            current_value=current_value,
            absolute_delta=difference,
            percentage_points=difference * 100 if metric_name in RATIO_METRICS else None,
            relative_percent=difference / baseline_value * 100 if baseline_value != 0 else None,
        )
    return ExperimentComparison(baseline=baseline, current=current, deltas=deltas)
