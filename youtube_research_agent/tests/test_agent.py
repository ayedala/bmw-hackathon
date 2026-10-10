from types import SimpleNamespace
import pytest
from agent import queries,select,validate_evidence,parse_observations
import agent
import requests


def test_daily_quota_does_not_retry(monkeypatch):
    response = requests.Response()
    response.status_code = 429
    response._content = b'{"error":{"message":"Quota exceeded: Search Queries per day"}}'
    calls = []
    monkeypatch.setattr(agent.requests, 'get', lambda *a, **kw: calls.append(kw) or response)
    monkeypatch.setattr(agent.time, 'sleep', lambda delay: pytest.fail('Daily quota must not retry'))
    with pytest.raises(requests.HTTPError, match='per day'):
        agent.yt_get('search', {}, 'secret')
    assert len(calls) == 1


def test_ip_block_stops_requests_but_processes_saved_transcripts(monkeypatch, tmp_path):
    from youtube_transcript_api._errors import IpBlocked
    monkeypatch.setenv('YOUTUBE_API_KEY', 'secret')
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    videos = [dict(video_id=vid, url='https://youtube.com/watch?v='+vid,
                   selected=True, retrieval_status='not_attempted')
              for vid in ('blocked', 'uncached', 'cached')]
    def discover(key, args):
        args.discovery_warnings = []
        return videos
    monkeypatch.setattr(agent, 'discover', discover)
    monkeypatch.setattr(agent, 'select', lambda found, args: found)
    calls = []
    def read(video_id, languages):
        calls.append(video_id)
        raise IpBlocked(video_id)
    monkeypatch.setattr(agent, 'read_transcript', read)
    segments = [dict(start=1, duration=2, text='Quiet cabin')]
    agent.cache_transcript(tmp_path, 'cached', ['en', 'de'], segments)
    assert agent.main(['--out', str(tmp_path)]) == 4
    assert calls == ['blocked']
    assert videos[1]['retrieval_status'] == 'skipped_ip_blocked'
    assert videos[2]['retrieval_status'] == 'retrieved'
    assert videos[2]['transcript_origin'] == 'saved'
    assert (tmp_path / 'transcripts/cached.json').exists()


def test_transcript_cache_language_scope_and_corruption(tmp_path):
    segments = [dict(start=1, duration=2, text='Quiet cabin')]
    agent.cache_transcript(tmp_path, 'abc', ['en'], segments)
    assert agent.cached_transcript(tmp_path, 'abc', ['en']) == segments
    assert agent.cached_transcript(tmp_path, 'abc', ['de']) is None
    (tmp_path / 'transcript_cache/abc.en.json').write_text('broken')
    assert agent.cached_transcript(tmp_path, 'abc', ['en']) is None


def test_rate_limit_retries_and_redacts(monkeypatch):
    calls, delays = [], []
    response = requests.Response()
    response.status_code = 429
    response._content = b'{"error":{"message":"Too many requests key=secret"}}'
    def get(*args, **kwargs):
        calls.append(kwargs)
        return response
    monkeypatch.setattr(agent.requests, 'get', get)
    monkeypatch.setattr(agent.time, 'sleep', delays.append)
    with pytest.raises(requests.HTTPError) as error:
        agent.yt_get('search', {}, 'secret')
    assert len(calls) == 3 and delays == [2, 4]
    assert 'secret' not in str(error.value)
    assert error.value.response.status_code == 429


def test_discovery_preserves_results_when_limited(monkeypatch):
    args = SimpleNamespace(vehicle='BMW', generation='G60', languages=['en'],
                           region='DE', from_date='2023-01-01', to_date='2026-10-10')
    saved = []
    args.discovery_checkpoint = lambda videos: saved.append(list(videos))
    response = requests.Response()
    response.status_code = 429
    response._content = b'{}'
    calls = []
    def get(endpoint, params, key):
        calls.append(endpoint)
        if len(calls) > 1:
            raise requests.HTTPError('limited', response=response)
        return {'items': [{'id': {'videoId': 'abc'}, 'snippet': {
            'title': 'BMW G60', 'channelTitle': 'test', 'channelId': 'ch',
            'publishedAt': '2025-01-01'}}], 'nextPageToken': 'next'}
    monkeypatch.setattr(agent, 'yt_get', get)
    videos = agent.discover('secret', args)
    assert [v['video_id'] for v in videos] == ['abc']
    assert saved[0][0]['video_id'] == 'abc'
    assert args.discovery_warnings and calls == ['search', 'search']


def test_rate_limit_without_results_is_not_success(monkeypatch, tmp_path):
    monkeypatch.setenv('YOUTUBE_API_KEY', 'secret')
    def discover(key, args):
        args.discovery_warnings = ['YouTube stopped accepting searches.']
        return []
    monkeypatch.setattr(agent, 'discover', discover)
    assert agent.main(['--out', str(tmp_path)]) == 3
    assert 'stopped accepting' in (tmp_path / 'summary.md').read_text()

def test_queries():
    q=queries('BMW 5 Series','G60',['en','de'])
    assert len(q)==8 and any('Langzeittest' in t for _,t in q)


def test_api_error_is_actionable_and_redacted(monkeypatch):
    import agent
    import requests
    key = 'synthetic-private-key'
    monkeypatch.setenv('YOUTUBE_API_KEY', key)
    response = requests.Response()
    response.status_code = 429
    response._content = b'{"error":{"message":"Daily search quota exhausted","errors":[{"reason":"rateLimitExceeded"}]}}'
    monkeypatch.setattr(agent.requests, 'get', lambda *a, **k: response)
    with pytest.raises(requests.HTTPError) as error:
        agent.yt_get('search', {}, key)
    assert 'rateLimitExceeded' in str(error.value)
    assert 'Daily search quota' in str(error.value)
    assert key not in agent.safe_error(f'https://example.test/?key={key}')


def test_probe_stops_discovery_after_matched_page(monkeypatch):
    import agent
    calls = []
    def get(endpoint, params, key):
        calls.append(endpoint)
        if endpoint == 'videos':
            return {'items': []}
        return {'nextPageToken': 'more', 'items': [dict(id={'videoId': 'abc'},
                snippet=dict(title='BMW 5 Series G60 review', channelTitle='ch',
                             channelId='ch', publishedAt='2025', description=''))]}
    monkeypatch.setattr(agent, 'yt_get', get)
    args = SimpleNamespace(vehicle='BMW 5 Series', generation='G60', languages=['en','de'],
                           region='DE', from_date='2023-01-01', to_date='2026-10-10',
                           max_videos=1, probe_only=True)
    assert len(agent.discover('synthetic', args)) == 1
    assert calls == ['search', 'videos']

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


@pytest.mark.parametrize('outcome,expected', [('no_candidates', 1), ('captions_failed', 1),
                                             ('extraction_failed', 1), ('completed_empty', 0)])
def test_run_reports_pipeline_outcome(outcome, expected, tmp_path, monkeypatch):
    import agent
    monkeypatch.setattr(agent, 'load_dotenv', lambda *a: None)
    monkeypatch.setenv('YOUTUBE_API_KEY', 'synthetic')
    monkeypatch.setenv('OPENAI_API_KEY', 'synthetic')
    video = dict(video_id='abc', url='url', title='BMW 5 Series G60', channel='ch',
                 channel_id='ch', published_at='2025', description='',
                 discovery_queries=['test'], retrieval_status='not_attempted')
    def discover(key, args):
        args.discovery_warnings = []
        return [] if outcome == 'no_candidates' else [video]
    monkeypatch.setattr(agent, 'discover', discover)
    def transcript(*args):
        if outcome == 'captions_failed':
            raise RuntimeError('Captions unavailable')
        return [dict(start=0, duration=1, text='Neutral description')]
    monkeypatch.setattr(agent, 'read_transcript', transcript)
    def extract(*args):
        if outcome == 'extraction_failed':
            raise RuntimeError('Extraction unavailable')
        return [], 'synthetic-session'
    monkeypatch.setattr(agent, 'agent_extract', extract)
    assert agent.main(['--out', str(tmp_path)]) == expected
    assert (tmp_path / 'summary.md').exists()
