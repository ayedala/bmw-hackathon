"""Authorized local media/transcript input; no YouTube network access."""
import base64
import hashlib
import json
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import requests
from dotenv import load_dotenv

import agent

MAX_BYTES = 24 * 1024 * 1024
MEDIA = {'.mp3', '.mp4', '.mpeg', '.mpga', '.m4a', '.wav', '.webm'}


@dataclass(frozen=True)
class Upload:
    video_id: str
    title: str
    vehicle: str
    generation: str
    suffix: str
    content: bytes

    @classmethod
    def parse(cls, data):
        if not isinstance(data, dict) or data.get('authorized') is not True:
            raise ValueError('Confirm this is authorized public material without private personal data before sending it to OpenAI.')
        video_id = str(data.get('video_id', '')).strip()
        if not re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id):
            raise ValueError('Provide the 11-character YouTube video ID from its link.')
        suffix = Path(str(data.get('filename', ''))).suffix.lower()
        if suffix not in MEDIA | {'.srt', '.vtt'}:
            raise ValueError('Choose an MP3, MP4, MPEG, MPGA, M4A, WAV, WEBM, SRT or VTT file.')
        try:
            content = base64.b64decode(data.get('content', ''), validate=True)
        except (ValueError, TypeError):
            raise ValueError('Invalid file encoding') from None
        if not 0 < len(content) <= MAX_BYTES:
            raise ValueError('Choose a nonempty file up to 24 MiB.')
        fields = [str(data.get(k, '')).strip() for k in ('title', 'vehicle', 'generation')]
        if any(not value or len(value) > 300 for value in fields):
            raise ValueError('Provide a title, vehicle and generation (up to 300 characters each).')
        return cls(video_id, *fields, suffix, content)


def subtitle_segments(content):
    text = content.decode('utf-8-sig').replace('\r\n', '\n').replace('\r', '\n')
    pattern = r'(?:(\d+):)?(\d{2}):(\d{2})[,.](\d{3})'
    def seconds(parts):
        h, m, s, ms = parts
        if int(m) >= 60 or int(s) >= 60:
            raise ValueError('Invalid subtitle timestamp')
        return int(h or 0)*3600 + int(m)*60 + int(s) + int(ms)/1000
    segments = []
    for block in re.split(r'\n\s*\n', text):
        lines = block.strip().splitlines()
        for index, line in enumerate(lines):
            if '-->' not in line:
                continue
            match = re.fullmatch(pattern + r'\s+-->\s+' + pattern + r'(?:\s+.*)?', line.strip())
            if not match:
                raise ValueError('Invalid subtitle timing line')
            start, end = seconds(match.groups()[:4]), seconds(match.groups()[4:])
            quote = '\n'.join(lines[index+1:]).strip()
            if end < start or not quote:
                raise ValueError('Subtitle needs text and a valid time interval')
            segments.append(dict(start=round(start, 2), duration=round(end-start, 2), text=quote))
            break
    if not segments:
        raise ValueError('No timestamped subtitles found in the file')
    return segments


def transcribe(path):
    key = os.getenv('OPENAI_API_KEY')
    if not key:
        raise ValueError('OPENAI_API_KEY is missing from the local .env file.')
    headers = {'Authorization': f'Bearer {key}'}
    if os.getenv('OPENAI_PROJECT_ID'):
        headers['OpenAI-Project'] = os.environ['OPENAI_PROJECT_ID']
    with path.open('rb') as media:
        response = requests.post('https://api.openai.com/v1/audio/transcriptions',
            headers=headers, files={'file': (path.name, media)},
            data={'model': 'whisper-1', 'response_format': 'verbose_json',
                  'timestamp_granularities[]': 'segment'}, timeout=300)
    if response.status_code >= 400:
        raise RuntimeError(f'OpenAI transcription failed (HTTP {response.status_code}). Check API billing, model permissions and file format. Original upload is saved locally.')
    result = response.json()
    segments = []
    for item in result.get('segments', []):
        start, end, text = float(item['start']), float(item['end']), item['text']
        if not all(math.isfinite(x) for x in (start, end)) or start < 0 or end < start or not isinstance(text, str):
            raise ValueError('Transcription returned invalid segments')
        segments.append(dict(start=round(start, 2), duration=round(end-start, 2), text=text))
    if not segments:
        raise ValueError('Transcription returned no timestamped speech')
    return segments


def process(upload, out, log):
    load_dotenv(Path(__file__).with_name('.env'))
    args = SimpleNamespace(vehicle=upload.vehicle, generation=upload.generation,
                           market='Not established from upload', languages=['unknown'],
                           from_date='Unknown', to_date='Unknown')
    video = dict(video_id=upload.video_id, url='https://www.youtube.com/watch?v='+upload.video_id,
        title=upload.title, channel='Unknown (user-supplied source)', published_at=None,
        selected=True, selection_reason='User supplied; vehicle/generation match requires evidence review',
        retrieval_status='not_attempted', transcript_origin='uploaded_subtitles' if upload.suffix in {'.srt', '.vtt'} else 'openai_whisper-1',
        source_sha256=hashlib.sha256(upload.content).hexdigest())
    out.mkdir(parents=True, exist_ok=True)
    original = out / ('original'+upload.suffix)
    original.write_bytes(upload.content)
    evidence, errors = [], []
    manifest = dict(video_id=upload.video_id, input_sha256=video['source_sha256'],
        source_binding='User asserted; not independently verified', model='whisper-1' if upload.suffix in MEDIA else None,
        extraction_agent=os.getenv('OPENAI_AGENT_ID'), transcription_mode=video['transcript_origin'])
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    try:
        log('Reading uploaded subtitles.' if upload.suffix not in MEDIA else 'Transcribing uploaded media with OpenAI (no YouTube requests).')
        if upload.suffix in MEDIA:
            # Content-addressed cache excludes vehicle/title: speech depends only on the bytes and model.
            cache = out.parent / '_media_cache' / (video['source_sha256']+'.whisper-1.json')
            if cache.exists():
                segments = json.loads(cache.read_text(encoding='utf-8'))
                video['transcript_origin'] = 'saved_whisper-1'
                log('Reusing the saved transcription of this file.')
            else:
                segments = transcribe(original)
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_text(json.dumps(segments, ensure_ascii=False), encoding='utf-8')
        else:
            segments = subtitle_segments(upload.content)
        (out / 'transcripts').mkdir(exist_ok=True)
        (out / 'transcripts' / (upload.video_id+'.json')).write_text(json.dumps(segments, ensure_ascii=False), encoding='utf-8')
        video.update(retrieval_status='retrieved', transcript_segments=len(segments))
        agent.save(out, [video], evidence, args, errors)
        log('Extracting findings and validating quotes against the transcript.')
        observations, session = agent.agent_extract(video, segments, args)
        evidence = agent.validate_evidence(observations, video, segments, args)
        video.update(extraction_status='completed', agent_session_id=session,
                     discarded_observations=len(observations)-len(evidence))
        log(f'Finished: {len(evidence)} validated findings. Transcript accuracy and source binding need human review.')
        return 0
    except Exception as error:
        message = agent.safe_error(error)[:500]
        errors.append(message)
        video['extraction_status' if video['retrieval_status']=='retrieved' else 'retrieval_status'] = 'failed'
        video['extraction_error' if video['retrieval_status']=='retrieved' else 'retrieval_error'] = message
        log(message)
        return 1
    finally:
        errors.append('Upload metadata and full-video timestamp alignment are user asserted, not independently verified. Speech transcription may contain errors. No YouTube search or caption download was performed.')
        agent.save(out, [video], evidence, args, errors)
