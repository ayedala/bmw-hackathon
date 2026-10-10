from types import SimpleNamespace
import pytest
from agent import queries,select,validate_evidence,parse_observations

def test_queries():
    q=queries('BMW 5 Series','G60',['en','de'])
    assert len(q)==8 and any('Langzeittest' in t for _,t in q)

def test_selection_dedup():
    v=[{'title':'BMW 5 Series G60 owner review','description':'','video_id':'x','channel_id':'a','published_at':'2025-01-01','discovery_queries':['x'],'selected':False}]
    a=SimpleNamespace(vehicle='BMW 5 Series',generation='G60',max_videos=10)
    assert len(select(v,a))==1

def test_quote_timestamp_validation():
    a=SimpleNamespace(vehicle='BMW 5 Series',generation='G60')
    video=dict(video_id='abc',url='url',title='title',channel='ch',published_at='2025')
    seg=[dict(start=10.0,text='The seats are comfortable.',duration=4)]
    obs=[dict(topic='seats',feedback_type='positive',supporting_excerpt='seats are comfortable',timestamp_seconds=10),dict(topic='seats',feedback_type='positive',supporting_excerpt='bad brakes',timestamp_seconds=10)]
    rows=validate_evidence(obs,video,seg,a)
    assert len(rows)==1 and rows[0]['timestamp_seconds']==10

def test_parse():
    assert parse_observations('```json\n{"observations":[]}\n```')==[]


def test_parse_rejects_missing_observations():
    with pytest.raises(ValueError):
        parse_observations('{"error":"extraction failed"}')


def test_generation_match_and_repeat_selection():
    args = SimpleNamespace(vehicle='BMW 5 Series', generation='G60', max_videos=10)
    videos = [dict(title=f'BMW 5 Series {generation}', description='',
                   video_id=generation, channel_id='a', published_at='2025-01-01',
                   discovery_queries=['x'], selected=False)
              for generation in ('G600', 'G60')]
    assert [v['video_id'] for v in select(videos, args)] == ['G60']
    assert [v['video_id'] for v in select(videos, args)] == ['G60']


def test_duplicate_segment_starts_and_malformed_observations():
    args = SimpleNamespace(vehicle='BMW 5 Series', generation='G60')
    video = dict(video_id='abc', url='url', title='title', channel='ch', published_at='2025')
    segments = [dict(start=10, text='Comfortable seats'), dict(start=10, text='Quiet cabin')]
    observations = [None, [], dict(timestamp_seconds=10, supporting_excerpt='Comfortable seats',
                                   feedback_type='positive')]
    assert len(validate_evidence(observations, video, segments, args)) == 1


@pytest.mark.parametrize('dates', [ ['--from-date', 'bad'],
                                   ['--from-date', '2026-01-01', '--to-date', '2025-01-01'] ])
def test_invalid_dates(dates, tmp_path):
    from agent import main
    with pytest.raises(SystemExit) as error:
        main(dates + ['--out', str(tmp_path / 'output')])
    assert error.value.code == 2
    assert not (tmp_path / 'output').exists()
