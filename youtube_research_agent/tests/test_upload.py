import base64
import json

import pytest
import upload_research as uploads
import web


SRT = b'1\n00:00:02,000 --> 00:00:04,500\nThe seats are comfortable.\n'


def payload(content=SRT, filename='review.srt'):
    return dict(video_id='aoXRE2kob0o', title='User supplied review', vehicle='BMW 5 Series',
                generation='G60', filename=filename, content=base64.b64encode(content).decode(), authorized=True)


def test_parse_subtitles_and_vtt():
    assert uploads.subtitle_segments(SRT) == [dict(start=2, duration=2.5, text='The seats are comfortable.')]
    assert uploads.subtitle_segments(b'WEBVTT\n\n00:02.000 --> 00:04.500 align:start\nQuiet cabin')[0]['start'] == 2


@pytest.mark.parametrize('content', [b'no timestamps', b'1\n00:00:05,000 --> 00:00:02,000\ntext',
                                      b'1\n00:99:05,000 --> 00:99:06,000\ntext'])
def test_invalid_subtitles(content):
    with pytest.raises(ValueError):
        uploads.subtitle_segments(content)


@pytest.mark.parametrize('change', [dict(authorized=False), dict(video_id='../secret'),
                                    dict(filename='run.exe'), dict(content='bad base64'), dict(title='')])
def test_upload_contract_rejects_bad_input(change):
    data = payload()
    data.update(change)
    with pytest.raises(ValueError):
        uploads.Upload.parse(data)


def test_subtitle_analysis_preserves_bytes_and_validates_quotes(monkeypatch, tmp_path):
    monkeypatch.setattr(uploads.requests, 'post', lambda *a, **k: pytest.fail('No transcription needed'))
    monkeypatch.setattr(uploads.agent, 'agent_extract', lambda *a: ([
        dict(timestamp_seconds=2, supporting_excerpt='seats are comfortable', feedback_type='positive'),
        dict(timestamp_seconds=2, supporting_excerpt='invented claim', feedback_type='positive')], 'test-session'))
    out = tmp_path / 'upload'
    assert uploads.process(uploads.Upload.parse(payload()), out, lambda x: None) == 0
    assert (out / 'original.srt').read_bytes() == SRT
    evidence = json.loads((out / 'evidence.json').read_text())
    assert len(evidence) == 1 and evidence[0]['timestamp_seconds'] == 2
    source = json.loads((out / 'sources.json').read_text())[0]
    assert source['published_at'] is None
    assert source['transcript_origin'] == 'uploaded_subtitles'


def test_media_transcription_reused_for_identical_bytes(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(uploads, 'transcribe', lambda path: calls.append(path) or uploads.subtitle_segments(SRT))
    monkeypatch.setattr(uploads.agent, 'agent_extract', lambda *a: ([], 'test-session'))
    item = uploads.Upload.parse(payload(b'fixture media bytes', 'review.mp3'))
    assert uploads.process(item, tmp_path/'one', lambda x: None) == 0
    assert uploads.process(item, tmp_path/'two', lambda x: None) == 0
    assert len(calls) == 1
    assert json.loads((tmp_path/'two/sources.json').read_text())[0]['transcript_origin'] == 'saved_whisper-1'


def test_transcription_failure_keeps_original(monkeypatch, tmp_path):
    def fail(path):
        raise RuntimeError('Model unavailable')
    monkeypatch.setattr(uploads, 'transcribe', fail)
    out = tmp_path/'failed'
    assert uploads.process(uploads.Upload.parse(payload(b'fixture', 'review.mp3')), out, lambda x: None) == 1
    assert (out/'original.mp3').read_bytes() == b'fixture'
    assert 'Model unavailable' in (out/'summary.md').read_text()
