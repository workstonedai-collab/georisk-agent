"""Explainable operational attention bands; never calibrated event probabilities."""
from datetime import datetime, timezone
from .memory import stamp


def priority(event,exposure):
    severity={'low':0,'moderate':1,'high':2,'critical':3}[event['severity']]
    reasons=['Event severity: '+event['severity']]
    deadline=exposure.get('deadline');near=False
    if deadline:
        days=(stamp(deadline)-datetime.now(timezone.utc)).total_seconds()/86400
        near=days<=7
        reasons.append('Operator deadline has passed' if days<0 else 'Operator deadline within seven days' if near else 'Operator deadline more than seven days away')
    importance=exposure.get('importance','medium');reasons.append('Operator importance: '+importance)
    band='urgent' if severity==3 or (severity>=2 and (near or importance=='high')) else 'watch' if severity>=1 or near else 'routine'
    return {'band':band,'reasons':reasons,'deadline':deadline,'note':'Qualitative attention order from saved severity, operator importance and deadline. It does not estimate event probability or order an automatic business action.'}
