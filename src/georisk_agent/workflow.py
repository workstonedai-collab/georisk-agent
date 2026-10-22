"""Source-linked event dossiers, private exposure matching and local change alerts."""
import re
import unicodedata
from .business import Records, choice, date, fields, fingerprint, strings, text
from .countries import scope_keys
from .decision import alert_details


class Workflow(Records):
    kinds = ('event', 'exposure', 'feedback')
    context_kinds = ('event', 'exposure')
    agent_kinds = ('event',)

    def __init__(self, store, product='georisk-agent'):
        super().__init__(store, product)

    @staticmethod
    def identity(data):
        def norm(s):
            return re.sub(r'\W+', '', unicodedata.normalize('NFKC', s).casefold())
        return fingerprint([norm(data['subject']), norm(data['location']), data['occurred_at'][:10]])

    def normalize(self, kind, data, as_of=None):
        if kind == 'event':
            fields(data, ['title','subject','location','occurred_at','published_at','countries','topics','summary','severity','confidence','status','impact','next_check','evidence_ids','change_note'])
            out = {k: text(data.get(k), 200 if k in ('title','subject','location') else 3000) for k in ('title','subject','location','summary','impact','next_check')}
            out.update(occurred_at=date(data.get('occurred_at')), published_at=date(data.get('published_at')),
                       countries=strings(data.get('countries')), topics=strings(data.get('topics')),
                       severity=choice(data.get('severity'), ('low','moderate','high','critical')),
                       confidence=choice(data.get('confidence'), ('unconfirmed','source_statement','corroborated')),
                       status=choice(data.get('status'), ('tracking','escalated','easing','closed')),
                       change_note=text(data.get('change_note',''), optional=True))
            if not out['countries'] or not out['topics']:
                raise ValueError('Event needs country and topic scope')
            if as_of and date(as_of) < out['published_at']:
                raise ValueError('Event was published after replay cutoff')
            out['evidence_ids'] = self.references(data.get('evidence_ids'), out['countries'], out['topics'], as_of)
            if not out['evidence_ids']:
                raise ValueError('Event requires at least one source record')
            return out
        if kind == 'exposure':
            fields(data, ['name','countries','topics','min_severity','active','note'])
            active = data.get('active', True)
            if type(active) is not bool:
                raise ValueError('active must be boolean')
            out = {'name':text(data.get('name'),200), 'countries':strings(data.get('countries',[])), 'topics':strings(data.get('topics',[])),
                   'min_severity':choice(data.get('min_severity','moderate'), ('low','moderate','high','critical')), 'active':active,
                   'note':text(data.get('note',''),optional=True)}
            if not out['countries'] and not out['topics']:
                raise ValueError('Exposure needs at least one country or topic constraint')
            return out
        if kind == 'feedback':
            fields(data, ['alert_id','state','note'])
            return {'alert_id':text(data.get('alert_id'),64), 'state':choice(data.get('state'),('seen','relevant','irrelevant','handled')),
                    'note':text(data.get('note',''),optional=True)}
        raise ValueError('Unknown risk record kind')

    def change(self, db, project, command, origin, run=None):
        if not isinstance(command, dict):
            raise ValueError('Project command must be an object')
        if command.get('kind') == 'event':
            command = dict(command)
            data = self.normalize('event', command.get('data'), run['mission'].get('as_of') if run else None)
            canonical = self.identity(data)
            same = next((e for e in self.list(db, project, 'event') if self.identity(e['data']) == canonical), None)
            if command.get('id') == 'auto':
                command['id'] = same['id'] if same else canonical
            elif same and same['id'] != command.get('id'):
                raise ValueError('Same event identity already exists as ' + same['id'])
            old = self.get(db, project, 'event', command['id'])
            if old:
                if self.identity(old['data']) != canonical:
                    raise ValueError('Event identity is immutable; create a distinct event')
                # A second URL enriches one dossier, not an independent new event.
                data['evidence_ids'] = sorted(set(data['evidence_ids'] + old['data']['evidence_ids']))
            command['data'] = data
        return super().change(db, project, command, origin, run)

    def validate_links(self, db, project, kind, rid, data, origin):
        if kind == 'feedback' and not self.get(db, project, 'alert', data['alert_id']):
            raise ValueError('Feedback refers to an unknown local alert')

    def state_in(self, db, project):
        return {'product':self.product, 'project_id':project, **{k:self.list(db,project,k) for k in self.kinds},
                'alerts':alert_details(self.store,self.list(db,project,'alert')), 'checks':self.list(db,project,'check'),
                'note':'Private project state. Event identity matches normalized subject/location/day, not unrestricted semantic clustering. Alerts are local qualitative assessments.'}

    def check(self, project):
        with self.store.tasks() as db:
            db.execute('BEGIN IMMEDIATE')
            return self.evaluate_in(db, project)

    def evaluate_in(self, db, project):
        created = []
        level = {n:i for i,n in enumerate(('low','moderate','high','critical'))}
        for event in self.list(db,project,'event'):
            e = event['data']
            for exposure in self.list(db,project,'exposure'):
                x = exposure['data']
                if not x['active'] or (x['countries'] and not scope_keys(x['countries']).intersection(scope_keys(e['countries']))) or (x['topics'] and not set(x['topics']).intersection(e['topics'])):
                    continue
                pair = fingerprint([event['id'],exposure['id']])
                old = self.get(db,project,'cursor',pair)
                if not old and (level[e['severity']] < level[x['min_severity']] or e['status']=='closed'):
                    continue
                signature = fingerprint({k:e[k] for k in ('severity','status','confidence','impact','next_check')})
                if old and old['data']['signature'] == signature:
                    continue
                revision = old['revision'] if old else 0
                aid = fingerprint([pair,revision,signature])
                payload = {'event_id':event['id'],'event_revision':event['revision'],'exposure_id':exposure['id'],
                    'title':e['title'],'exposure':x['name'],'severity':e['severity'],'confidence':e['confidence'],'status':e['status'],
                    'change':'initial_match' if not old else 'changed_assessment','previous':old['data'].get('assessment') if old else None,
                    'assessment':{k:e[k] for k in ('severity','status','confidence','impact','next_check')},
                    'why_relevant':{'countries':sorted(scope_keys(x['countries']).intersection(scope_keys(e['countries']))), 'topics':sorted(set(x['topics']).intersection(e['topics']))},
                    'change_note':e['change_note'],'evidence_ids':e['evidence_ids'], 'published_at':e['published_at'],
                    'note':'Qualitative source-linked alert, not a calibrated probability or automatic routing instruction.'}
                self.save(db,project,'alert',aid,payload,0,'runtime')
                self.save(db,project,'cursor',pair,{'signature':signature,'assessment':payload['assessment']},revision,'runtime')
                created.append(aid)
        old = self.get(db,project,'check','latest')
        from datetime import datetime, timezone
        check = {'evaluated_at':datetime.now(timezone.utc).isoformat(), 'evaluated_events':len(self.list(db,project,'event')),'alerts_created':len(created),'alert_ids':created,
                 'scope':'saved_project_events_only','source_refresh':'not_performed','registered_sources':len(self.store.sources()),
                 'note':'No new local alert does not prove no external event. Run research or refresh registered sources to acquire current evidence.'}
        saved = self.save(db,project,'check','latest',check,old['revision'] if old else 0,'runtime')
        return {**check, 'checked_at':saved['updated']}

    def guide(self):
        return {'product':self.product,'agent_writable_kinds':list(self.agent_kinds),
            'event_contract':{'kind':'event','id':'auto or an existing event ID','expected_revision':0,
            'data':{'title':'source-linked event','subject':'canonical subject','location':'canonical place','occurred_at':'ISO date',
            'published_at':'ISO date','countries':['mission country'],'topics':['mission topic'],'summary':'source statement',
            'severity':'low/moderate/high/critical','confidence':'unconfirmed/source_statement/corroborated','status':'tracking/escalated/easing/closed',
            'impact':'reasoned transmission to operations, with uncertainty','next_check':'observable condition/source','change_note':'what changed', 'evidence_ids':['read ID']}},
            'report_extension':'Optional project_update: {commands:[event_contract]}. Read project_state for existing IDs/revisions. Matching identity does not prove independent corroboration. Do not alter private exposures. Report saves directly; conflicts retain report without overwriting operator state.'}
