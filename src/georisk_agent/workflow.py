"""Source-linked event dossiers, private exposure matching and local change alerts."""
import re
import unicodedata
from .business import Records, choice, date, fields, fingerprint, strings, text
from .countries import scope_keys
from .decision import alert_details


class Workflow(Records):
    kinds = ('event', 'exposure', 'feedback', 'event_alias', 'event_merge')
    context_kinds = ('event', 'exposure', 'event_alias', 'event_merge')
    agent_kinds = ('event',)

    def __init__(self, store, product='georisk-agent'):
        super().__init__(store, product)

    @staticmethod
    def identity(data):
        def norm(s):
            return re.sub(r'\W+', '', unicodedata.normalize('NFKC', s).casefold())
        return fingerprint([norm(data['subject']), norm(data['location']), data['occurred_at'][:10]])

    def normalize(self, kind, data, as_of=None):
        if kind == 'event_alias':
            fields(data,['subject','location','occurred_at','target_event_id','reason'])
            return {'subject':text(data.get('subject'),200),'location':text(data.get('location'),200),
                    'occurred_at':date(data.get('occurred_at')),'target_event_id':text(data.get('target_event_id'),64),'reason':text(data.get('reason'))}
        if kind == 'event_merge':
            fields(data,['source_id','target_id','reason'])
            return {'source_id':text(data.get('source_id'),64),'target_id':text(data.get('target_id'),64),'reason':text(data.get('reason'))}
        if kind == 'event':
            fields(data, ['title','subject','location','occurred_at','published_at','countries','topics','summary','severity','confidence','status','impact','next_check','evidence_ids','change_note','entity_keys'])
            out = {k: text(data.get(k), 200 if k in ('title','subject','location') else 3000) for k in ('title','subject','location','summary','impact','next_check')}
            out.update(occurred_at=date(data.get('occurred_at')), published_at=date(data.get('published_at')),
                       countries=strings(data.get('countries')), topics=strings(data.get('topics')),
                       severity=choice(data.get('severity'), ('low','moderate','high','critical')),
                       confidence=choice(data.get('confidence'), ('unconfirmed','source_statement','corroborated')),
                       status=choice(data.get('status'), ('tracking','escalated','easing','closed')),
                       change_note=text(data.get('change_note',''), optional=True))
            if 'entity_keys' in data:out['entity_keys']=strings(data['entity_keys'])
            if not out['countries'] or not out['topics']:
                raise ValueError('Event needs country and topic scope')
            if as_of and date(as_of) < out['published_at']:
                raise ValueError('Event was published after replay cutoff')
            out['evidence_ids'] = self.references(data.get('evidence_ids'), out['countries'], out['topics'], as_of)
            if not out['evidence_ids']:
                raise ValueError('Event requires at least one source record')
            return out
        if kind == 'exposure':
            fields(data, ['name','countries','topics','min_severity','active','note','object_type','entity_keys','deadline','importance'])
            active = data.get('active', True)
            if type(active) is not bool:
                raise ValueError('active must be boolean')
            out = {'name':text(data.get('name'),200), 'countries':strings(data.get('countries',[])), 'topics':strings(data.get('topics',[])),
                   'min_severity':choice(data.get('min_severity','moderate'), ('low','moderate','high','critical')), 'active':active,
                   'note':text(data.get('note',''),optional=True)}
            if 'object_type' in data:out['object_type']=choice(data['object_type'],('route','port','supplier','project','country','other'))
            if 'entity_keys' in data:out['entity_keys']=strings(data['entity_keys'])
            if data.get('deadline'):out['deadline']=date(data['deadline'])
            if 'importance' in data:out['importance']=choice(data['importance'],('low','medium','high'))
            if not out['countries'] and not out['topics']:
                raise ValueError('Exposure needs at least one country or topic constraint')
            return out
        if kind == 'feedback':
            fields(data, ['alert_id','state','note'])
            return {'alert_id':text(data.get('alert_id'),64), 'state':choice(data.get('state'),('seen','relevant','irrelevant','handled')),
                    'note':text(data.get('note',''),optional=True)}
        raise ValueError('Unknown risk record kind')

    def canonical(self,db,project,eid):
        seen=set()
        while True:
            if eid in seen:raise ValueError('Event merge cycle')
            seen.add(eid)
            link=self.get(db,project,'event_merge',eid)
            if not link:return eid
            eid=link['data']['target_id']

    def change(self, db, project, command, origin, run=None):
        if not isinstance(command, dict):
            raise ValueError('Project command must be an object')
        if command.get('kind') == 'event':
            command = dict(command)
            data = self.normalize('event', command.get('data'), run['mission'].get('as_of') if run else None)
            canonical = self.identity(data)
            same = next((e for e in self.list(db, project, 'event') if self.identity(e['data']) == canonical), None)
            alias=next((a for a in self.list(db,project,'event_alias') if self.identity(a['data'])==canonical),None)
            if alias:same=self.get(db,project,'event',self.canonical(db,project,alias['data']['target_event_id']))
            elif same:same=self.get(db,project,'event',self.canonical(db,project,same['id']))
            mapped=bool(same and self.identity(same['data'])!=canonical)
            if command.get('id') == 'auto':
                command['id'] = same['id'] if same else canonical
            elif same and same['id'] != command.get('id'):
                raise ValueError('Same event identity already exists as ' + same['id'])
            if self.canonical(db,project,command['id'])!=command['id']:raise ValueError('Event was merged; update its canonical target')
            old = self.get(db, project, 'event', command['id'])
            if (alias or mapped) and old and same and old['id']==same['id']:
                for key in ('subject','location','occurred_at'):data[key]=old['data'][key]
                canonical=self.identity(data)
            if old:
                if self.identity(old['data']) != canonical:
                    raise ValueError('Event identity is immutable; create a distinct event')
                if 'entity_keys' in old['data']:data.setdefault('entity_keys',old['data']['entity_keys'])
                # A second URL enriches one dossier, not an independent new event.
                data['evidence_ids'] = sorted(set(data['evidence_ids'] + old['data']['evidence_ids']))
            command['data'] = data
        if command.get('kind')=='event_merge':
            if origin!='operator':raise ValueError('Only operator can merge event dossiers')
            data=self.normalize('event_merge',command.get('data'))
            source,target=data['source_id'],data['target_id']
            if command.get('id')!=source:raise ValueError('Merge record ID must equal source event ID')
            if source==target or self.canonical(db,project,target)==source:raise ValueError('Event merge cycle')
            if self.get(db,project,'event_merge',source):raise ValueError('Event already merged; merge history is retained')
            if self.canonical(db,project,target)!=target:raise ValueError('Choose the canonical target event')
            source_row=self.get(db,project,'event',source);target_row=self.get(db,project,'event',target)
            if not source_row or not target_row:raise ValueError('Merge requires two saved events')
            left,right=source_row['data'],target_row['data']
            if not scope_keys(left['countries']).intersection(scope_keys(right['countries'])) or not set(left['topics']).intersection(right['topics']):raise ValueError('Merge requires overlapping country and topic scope')
            merged=dict(right,evidence_ids=sorted(set(left['evidence_ids']+right['evidence_ids'])),change_note='Operator dossier merge: '+data['reason'])
            self.references(merged['evidence_ids'],right['countries'],right['topics'])
            self.save(db,project,'event',target,merged,target_row['revision'],'operator')
        return super().change(db, project, command, origin, run)

    def validate_links(self, db, project, kind, rid, data, origin):
        if kind=='event_alias':
            if origin!='operator':raise ValueError('Only operator can register an event alias')
            target=self.canonical(db,project,data['target_event_id'])
            if not self.get(db,project,'event',target):raise ValueError('Alias target must be a saved event')
            data['target_event_id']=target
            identity=self.identity(data)
            existing=next((e for e in self.list(db,project,'event') if self.identity(e['data'])==identity and self.canonical(db,project,e['id'])!=target),None)
            if existing:raise ValueError('Alias matches another saved event; explicitly merge dossiers first')
            duplicate=next((r for r in self.list(db,project,'event_alias') if r['id']!=rid and self.identity(r['data'])==identity),None)
            if duplicate:raise ValueError('This alias is already registered')
        if kind == 'feedback' and not self.get(db, project, 'alert', data['alert_id']):
            raise ValueError('Feedback refers to an unknown local alert')

    def state_in(self, db, project):
        value={'product':self.product, 'project_id':project, **{k:self.list(db,project,k) for k in self.kinds},
                'alerts':alert_details(self.store,self.list(db,project,'alert')), 'checks':self.list(db,project,'check'),
                'note':'Private project state. Event identity uses normalized subject/location/day plus explicit operator aliases/merges; no automatic semantic clustering. Event revisions retain evolution. Alerts are local qualitative assessments.'}

        latest={}
        active={r['id'] for r in value['exposure'] if r['data']['active']}
        for row in value['alerts']:
            data=row['data']
            if data['exposure_id'] in active and self.canonical(db,project,data['event_id'])==data['event_id']:
                latest[(data['event_id'],data['exposure_id'])]=row
        order={'urgent':0,'watch':1,'routine':2}
        value['attention_queue']=sorted([r for r in latest.values() if r['data']['status']!='closed'],key=lambda r:(order.get(r['data'].get('priority',{}).get('band'),1),r['id']))
        return value

    def check(self, project):
        with self.store.tasks() as db:
            db.execute('BEGIN IMMEDIATE')
            return self.evaluate_in(db, project)

    def evaluate_in(self, db, project):
        created = []
        level = {n:i for i,n in enumerate(('low','moderate','high','critical'))}
        for event in self.list(db,project,'event'):
            if self.canonical(db,project,event['id'])!=event['id']:continue
            e = event['data']
            for exposure in self.list(db,project,'exposure'):
                x = exposure['data']
                if not x['active'] or (x['countries'] and not scope_keys(x['countries']).intersection(scope_keys(e['countries']))) or (x['topics'] and not set(x['topics']).intersection(e['topics'])):
                    continue
                ekeys=set(e.get('entity_keys',[]));xkeys=set(x.get('entity_keys',[]))
                if ekeys and xkeys and not ekeys.intersection(xkeys):continue
                from .risk_paths import priority
                attention=priority(e,x)
                pair = fingerprint([event['id'],exposure['id']])
                old = self.get(db,project,'cursor',pair)
                if not old and (level[e['severity']] < level[x['min_severity']] or e['status']=='closed'):
                    continue
                signature = fingerprint({'assessment':{k:e[k] for k in ('severity','status','confidence','impact','next_check')},'exposure':x,'priority':attention})
                if old and old['data']['signature'] == signature:
                    continue
                revision = old['revision'] if old else 0
                aid = fingerprint([pair,revision,signature])
                payload = {'event_id':event['id'],'event_revision':event['revision'],'exposure_id':exposure['id'],
                    'title':e['title'],'exposure':x['name'],'severity':e['severity'],'confidence':e['confidence'],'status':e['status'],
                    'change':'initial_match' if not old else 'changed_assessment','previous':old['data'].get('assessment') if old else None,
                    'assessment':{k:e[k] for k in ('severity','status','confidence','impact','next_check')},
                    'why_relevant':{'countries':sorted(scope_keys(x['countries']).intersection(scope_keys(e['countries']))), 'topics':sorted(set(x['topics']).intersection(e['topics']))},
                    'priority':attention,'entity_match':{'event_keys':sorted(ekeys),'exposure_keys':sorted(xkeys),'matched_keys':sorted(ekeys&xkeys),'basis':'explicit_keys' if ekeys&xkeys else 'country_topic_only'},
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
        return {'product':self.product,'dossier_guidance':'Read event_alias/event_merge when identifying saved events. Aliases/merges are operator-confirmed. Entity keys are explicit private business links; country/topic-only matching must be labeled. Read exposure deadlines and importance without changing them. Event revisions retain source-backed evolution; no automatic external action.','agent_writable_kinds':list(self.agent_kinds),
            'event_contract':{'kind':'event','id':'auto or an existing event ID','expected_revision':0,
            'data':{'title':'source-linked event','subject':'canonical subject','location':'canonical place','occurred_at':'ISO date',
            'published_at':'ISO date','countries':['mission country'],'topics':['mission topic'],'summary':'source statement',
            'severity':'low/moderate/high/critical','confidence':'unconfirmed/source_statement/corroborated','status':'tracking/escalated/easing/closed',
            'impact':'reasoned transmission to operations, with uncertainty','next_check':'observable condition/source','change_note':'what changed', 'evidence_ids':['read ID']}},
            'report_extension':'Optional project_update: {commands:[event_contract]}. Read project_state for existing IDs/revisions. Matching identity does not prove independent corroboration. Do not alter private exposures. Report saves directly; conflicts retain report without overwriting operator state.'}
