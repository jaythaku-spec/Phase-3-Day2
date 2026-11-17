from models import Alert

_NEXT_STEPS = {
    "critical": "Investigate immediately and take corrective action.",
    "warning": "Review the affected system and monitor the metric closely.",
    "info": "Review the metric and confirm whether any action is needed.",
}


def generate_explanation(alert: Alert) -> str:
    if alert.metric_value > alert.threshold:
        comparison = "exceeded"
    elif alert.metric_value < alert.threshold:
        comparison = "fell below"
    else:
        comparison = "reached"

    next_step = _NEXT_STEPS[alert.severity]
    return (
        f'This {alert.severity} alert from {alert.source} is titled "{alert.title}". '
        f"The {alert.metric_name} metric {comparison} its threshold: the current "
        f"value is {alert.metric_value}, compared with a threshold of "
        f"{alert.threshold}. Recommended next step: {next_step}"
    )
