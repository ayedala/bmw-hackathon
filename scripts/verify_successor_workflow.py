"""Real-data automated UI rehearsal on a copy; all decisions are illustrative test input."""
from pathlib import Path
import sqlite3,json,os
from uuid import uuid4
from streamlit.testing.v1 import AppTest
from bmw_pm.storage import Database
from bmw_pm.decision.planning import PriorityService
from bmw_pm.validation import validate_database
path=Path('data/processed') / ('illustrative-reviewed-draft-'+uuid4().hex+'.db')
with sqlite3.connect('data/processed/bmw_pm.db') as src, sqlite3.connect(path) as dst: src.backup(dst)
db=Database(path);db.initialize()
os.environ['BMW_PM_DATABASE']=str(path.resolve())
app=AppTest.from_file(str(Path('ui/app.py').resolve()),default_timeout=30).run()
next(x for x in app.text_input if x.label=='SQLite database').set_value(str(path)).run()
assert not app.exception,[e.message for e in app.exception]
req=next(i['requirement'] for i in db.requirement_summaries() if i['requirement'].title=='Controls Usability' and i['requirement'].scope.models==['G60'])
next(x for x in app.button if x.key==f'select_{req.requirement_id}').click().run()
next(x for x in app.text_input if x.label=='Planning reviewer ID').set_value('illustrative-ui-test-pm')
next(x for x in app.text_area if x.label=='Draft adoption rationale (required)').set_value('ILLUSTRATIVE UI CHECK: distinguish access and discoverability, compare controls before hardware commitment.')
next(x for x in app.button if x.label=='Adopt draft as reviewable revision').click().run()
assert not app.exception,[e.message for e in app.exception]
new=db.latest_requirement(req.requirement_id)
assert new.revision==req.revision+1
assert db.latest_score(req.requirement_id,new.revision) is None
next(x for x in app.button if x.label=='Use AI suggestion as editable draft inputs').click().run()
assert not app.exception,[e.message for e in app.exception]
assert not PriorityService(db).history(req.requirement_id)
next(x for x in app.number_input if x.label=='Priority uncertainty').set_value(3)
next(x for x in app.text_area if x.label=='Priority rationale (required)').set_value('ILLUSTRATIVE UI CHECK: higher uncertainty because discoverability may explain part of the complaint.')
next(x for x in app.button if x.label=='Save priority assessment').click().run()
assert not app.exception,[e.message for e in app.exception]
assessment=PriorityService(db).history(req.requirement_id)[-1]
assert assessment.requirement_revision==new.revision and assessment.factors.uncertainty==3
assert not assessment.priority_confirmed
next(x for x in app.button if x.label=='Use AI suggestion as editable draft inputs').click().run()
next(x for x in app.number_input if x.label=='Priority uncertainty').set_value(3)
next(x for x in app.checkbox if x.label=='I explicitly confirm this priority as the reviewer').check()
next(x for x in app.text_area if x.label=='Priority rationale (required)').set_value('ILLUSTRATIVE UI CHECK: explicitly confirm concept-study priority only; not BMW sign-off.')
next(x for x in app.button if x.label=='Save priority assessment').click().run()
assert not app.exception,[e.message for e in app.exception]
assessment=PriorityService(db).history(req.requirement_id)[-1]
assert assessment.priority_confirmed
next(x for x in app.text_input if x.label=='Reviewer ID (declared, not verified)').set_value('illustrative-ui-test-pm')
next(x for x in app.text_area if x.label=='Decision rationale (required)').set_value('ILLUSTRATIVE UI CHECK: conditional concept-testing approval only; not BMW sign-off.')
next(x for x in app.checkbox if x.label.startswith('For approval:')).check().run()
next(x for x in app.button if x.label=='Approve').click().run()
assert not app.exception,[e.message for e in app.exception]
replay=db.replay_requirement(req.requirement_id)
assert replay['decisions'][-1]['action']=='approve'
assert replay['decisions'][-1]['priority_assessment_id']==assessment.assessment_id
other=next(i['requirement'] for i in db.requirement_summaries() if i['requirement'].title=='Software Reliability' and i['requirement'].scope.models==['G60'])
next(x for x in app.button if x.key==f'select_{other.requirement_id}').click().run()
next(x for x in app.text_input if x.label=='Planning reviewer ID').set_value('illustrative-ui-test-pm')
next(x for x in app.text_area if x.label=='Draft adoption rationale (required)').set_value('ILLUSTRATIVE UI CHECK: adopt the specific future draft for an explicit rejection decision.')
next(x for x in app.button if x.label=='Adopt draft as reviewable revision').click().run()
next(x for x in app.text_input if x.label=='Reviewer ID (declared, not verified)').set_value('illustrative-ui-test-pm')
next(x for x in app.text_area if x.label=='Decision rationale (required)').set_value('ILLUSTRATIVE UI CHECK: reject commitment pending matched app/vehicle telemetry and recovery-task validation; retain the concept for further research. Not BMW sign-off.')
app.run()
next(x for x in app.button if x.label=='Reject').click().run()
assert not app.exception,[e.message for e in app.exception]
assert db.replay_requirement(other.requirement_id)['decisions'][-1]['action']=='reject'
next(x for x in app.button if x.label=='Prepare private decision brief').click().run()
assert not app.exception,[e.message for e in app.exception]
assert 'planning_export' in app.session_state
path.with_suffix('.md').write_text('ILLUSTRATIVE AUTOMATED UI REHEARSAL; NOT BMW SIGN-OFF.\n\n' + app.session_state['planning_export'][3],encoding='utf-8')
next(x for x in app.radio if x.label=='Workspace').set_value('Data & AI findings').run()
assert not app.exception,[e.message for e in app.exception]
assert any(x.value=='Combined evidence assessment' for x in app.subheader)
next(x for x in app.radio if x.label=='Workspace').set_value('Audit trail').run()
assert not app.exception,[e.message for e in app.exception]
assert any('Audit chain verified' in x.value for x in app.success)
validation=validate_database(db,expect_supplied_shape=True)
assert validation['passed'],validation
report={'ui_exceptions':len(app.exception),'workflow':['adopt as immutable revision','seed editable AI values without saving','save PM draft priority','explicitly confirm priority','approve','reject','export','replay'],'database':str(path),'validation':validation,'illustrative_decisions_only':True}
Path('data/processed/successor-ui-verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('UI workflow passed: adopt, revision, saved priority, approve, reject, export and replay; copied dataset valid.')
