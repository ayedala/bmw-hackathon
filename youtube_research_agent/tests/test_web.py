import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

import pytest
import web


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setattr(web, 'OUTPUT', tmp_path)
    run = tmp_path / 'example'
    (run / 'transcripts').mkdir(parents=True)
    (run / 'sources.json').write_text('[{"video_id":"abc"}]', encoding='utf-8')
    (run / 'evidence.json').write_text('[]', encoding='utf-8')
    (run / 'transcripts' / 'abc.json').write_text('[{"start":10,"text":"Quiet cabin"}]', encoding='utf-8')
    instance = ThreadingHTTPServer(('127.0.0.1', 0), web.Handler)
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    yield instance.server_address[1]
    instance.shutdown()
    instance.server_close()
    thread.join()


def request(port, path, method='GET', body=None, headers=None):
    connection = HTTPConnection('127.0.0.1', port)
    connection.request(method, path, body, headers or {})
    response = connection.getresponse()
    status, content = response.status, response.read()
    connection.close()
    return status, content


def test_saved_runs_and_transcripts(server):
    assert json.loads(request(server, '/api/runs')[1]) == ['example']
    result = json.loads(request(server, '/api/results?run=example')[1])
    assert result['sources'] == [{'video_id': 'abc'}]
    transcript = json.loads(request(server, '/api/transcript?run=example&video=abc')[1])
    assert transcript[0]['text'] == 'Quiet cabin'
    assert request(server, '/')[0] == 200


def test_paths_cannot_escape_output(server):
    assert request(server, '/api/results?run=../../')[0] == 400
    assert request(server, '/api/transcript?run=example&video=../secret')[0] == 400


def test_cross_origin_run_rejected(server):
    assert request(server, '/api/run', 'POST', '{}', {'Origin': 'https://example.com'})[0] == 403


def test_run_passes_form_as_arguments(server, monkeypatch):
    commands = []
    monkeypatch.setattr(web, 'execute', lambda command: commands.append(command))
    body = json.dumps({'vehicle': 'BMW 5 Series', 'generation': 'G60', 'market': 'Europe',
                       'region': 'DE', 'from-date': '2023-01-01', 'to-date': '2026-10-10',
                       'max-videos': 1, 'languages': 'en de', 'probe': True})
    try:
        status, _ = request(server, '/api/run', 'POST', body,
                            {'Origin': f'http://127.0.0.1:{server}'})
        assert status == 200
        # Wait for the worker to enter the stub without relying on a fixed delay.
        for thread in threading.enumerate():
            if thread is not threading.current_thread() and thread.name.endswith('(execute)'):
                thread.join(timeout=1)
        assert commands and '--probe-only' in commands[0]
        assert commands[0][commands[0].index('--vehicle') + 1] == 'BMW 5 Series'
    finally:
        with web.LOCK:
            web.STATE['running'] = False
