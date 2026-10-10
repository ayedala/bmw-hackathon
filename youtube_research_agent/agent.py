"""CLI-only YouTube evidence research; no user-supplied video links needed."""
import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

API = 'https://www.googleapis.com/youtube/v3'
OPENAI_API = 'https://api.openai.com/v1/agents/sessions'
FIELDS = ['video_id','url','title','channel','published_at','vehicle','generation','configuration', 'market_evidence','speaker_type','topic','feedback_type','source_statement','supporting_excerpt','timestamp_seconds','customer_need_inferred','uncertainties']


def queries(vehicle, generation, languages):
    labels = {'en': ['owner review', 'long term review', 'problems complaints', 'likes dislikes improvements'],
              'de': ['Erfahrungsbericht Besitzer', 'Langzeittest', 'Probleme Kritik', 'Stärken Schwächen Verbesserungen']}
    result = []
    for lang in languages:
        for ending in labels.get(lang, [f'{lang} review', f'{lang} problems']):
            result.append((lang, f'{vehicle} {generation} {ending}'))
    return result


def safe_error(error):
    text = str(error)
    for name in ('YOUTUBE_API_KEY', 'OPENAI_API_KEY'):
        if os.getenv(name):
            text = text.replace(os.environ[name], '[REDACTED]')
    return re.sub(r'([?&]key=)[^&\s]+', r'\1[REDACTED]', text)


def yt_get(endpoint, params, api_key):
    for attempt in range(3):
        try:
            response = requests.get(f'{API}/{endpoint}', params={**params,'key': api_key}, timeout=30)
        except requests.RequestException as error:
            raise RuntimeError(safe_error(error).replace(api_key, '[REDACTED]')) from None
        daily_quota = response.status_code >= 400 and ('per day' in response.text.lower() or 'dailylimitexceeded' in response.text.lower())
        if not daily_quota and (response.status_code == 429 or response.status_code >= 500):
            if attempt < 2:
                try:
                    delay = min(30, max(2 ** (attempt + 1), float(response.headers.get('Retry-After', 0))))
                except ValueError:
                    delay = 2 ** (attempt + 1)
                print(f'YouTube is temporarily limiting requests (HTTP {response.status_code}); retrying in {delay:g}s.', flush=True)
                time.sleep(delay)
                continue
        if response.status_code >= 400:
            try:
                error = response.json().get('error', {})
                detail = error.get('message', '')
                reasons = ', '.join(str(item.get('reason', 'unknown')) for item in error.get('errors', []))
            except (ValueError, AttributeError):
                detail = ''
                reasons = 'unknown'
            message = f'YouTube {endpoint}: HTTP {response.status_code}. {reasons}; {detail}'
            message = safe_error(message.replace(api_key, '[REDACTED]'))
            raise requests.HTTPError(message, response=response)
        return response.json()


def discover(api_key, args):
    all_videos = {}
    args.discovery_videos = []
    region = args.region.upper()
    args.discovery_warnings = []
    stop_search = False
    for lang, query in queries(args.vehicle, args.generation, args.languages):
        page_token = None
        while True:
            params = dict(part='snippet', type='video', q=query, maxResults=50, order='relevance',
                          relevanceLanguage=lang, regionCode=region,
                          publishedAfter=args.from_date+'T00:00:00Z', publishedBefore=args.to_date+'T23:59:59Z')
            if page_token:
                params['pageToken'] = page_token
            try:
                data = yt_get('search', params, api_key)
            except requests.HTTPError as ex:
                try:
                    reasons = {item.get('reason') for item in ex.response.json().get('error', {}).get('errors', [])}
                except (AttributeError, ValueError):
                    reasons = set()
                if ex.response.status_code == 429 or reasons.intersection({'quotaExceeded', 'dailyLimitExceeded', 'rateLimitExceeded', 'userRateLimitExceeded'}):
                    daily = 'per day' in str(ex).lower() or 'dailyLimitExceeded' in reasons
                    args.discovery_warnings.append(
                        ('YouTube daily search allowance is exhausted. Wait for the quota to reset or request a quota increase in Google Cloud. '
                         if daily else 'YouTube stopped accepting searches. Temporary limits were retried; check YouTube Data API quotas in Google Cloud before retrying if this persists. ')
                        + f'Processing {len(all_videos)} videos found so far. {safe_error(ex)}')
                    stop_search = True
                    break
                raise
            for x in data.get('items', []):
                vid = x.get('id', {}).get('videoId')
                if not vid: continue
                sn = x['snippet']
                if vid not in all_videos:
                    all_videos[vid] = {'video_id':vid, 'url':f'https://www.youtube.com/watch?v={vid}',
                      'title':sn['title'], 'channel':sn['channelTitle'], 'channel_id':sn['channelId'],
                      'published_at':sn['publishedAt'], 'description':sn.get('description',''),
                      'discovery_queries':[], 'language_queries':[], 'retrieval_status':'not_attempted',
                      'selection_reason':None, 'selected':False}
                if query not in all_videos[vid]['discovery_queries']:
                    all_videos[vid]['discovery_queries'].append(query)
                if lang not in all_videos[vid]['language_queries']:
                    all_videos[vid]['language_queries'].append(lang)
            args.discovery_videos = list(all_videos.values())
            if getattr(args, 'discovery_checkpoint', None):
                args.discovery_checkpoint(args.discovery_videos)
            page_token = data.get('nextPageToken')
            if getattr(args, 'probe_only', False) and select(list(all_videos.values()), args):
                stop_search = True
                break
            if not page_token:
                break
        if stop_search:
            break
    ids = list(all_videos)
    if stop_search and args.discovery_warnings:
        return list(all_videos.values())
    for i in range(0,len(ids),50):
        for x in yt_get('videos', dict(part='snippet,contentDetails,status',id=','.join(ids[i:i+50])), api_key).get('items',[]):
            v = all_videos[x['id']]
            v['duration_iso8601'] = x.get('contentDetails',{}).get('duration')
            v['caption_flag'] = x.get('contentDetails',{}).get('caption')
            v['default_audio_language'] = x.get('snippet',{}).get('defaultAudioLanguage')
            v['privacy_status'] = x.get('status',{}).get('privacyStatus')
    return list(all_videos.values())


def select(videos,args):
    selected=[]; counts=Counter()
    model_tokens = [t.lower() for t in args.vehicle.split() if len(t)>1]
    gen = args.generation.lower()
    gen_pattern = re.compile(r'(?<!\w)' + re.escape(gen) + r'(?!\w)')
    for v in videos:
        v['selected'] = False
        title = v['title'].lower(); description = v['description'].lower()
        combined = title+' '+description
        title_has_gen = bool(gen_pattern.search(title))
        mentions_gen = bool(gen_pattern.search(combined))
        has_vehicle = all(t in combined for t in model_tokens)
        unrelated = bool(re.search(r'\b(f10|g30|e60|f11)\b',title)) and not title_has_gen
        v['relevance_score'] = (5 if title_has_gen else 0)+(3 if mentions_gen else 0)+(2 if has_vehicle else 0)+min(len(v['discovery_queries']),4)
        if not mentions_gen or not has_vehicle or unrelated:
            v['selection_reason']='rejected: generation/vehicle unconfirmed or competing generation'
            continue
        v['selection_reason']='generation and vehicle matched metadata; discovered via '+', '.join(v['discovery_queries'][:2])
    ranking=sorted([v for v in videos if v['selection_reason'] and not v['selection_reason'].startswith('rejected')],key=lambda x:(-x['relevance_score'], x['published_at']))
    while args.max_videos == 0 or len(selected)<args.max_videos:
        available=[v for v in ranking if not v['selected']]
        if not available:break
        v=min(available,key=lambda x:(counts[x['channel_id']], -x['relevance_score']))
        v['selected']=True;selected.append(v);counts[v['channel_id']]+=1
    return selected


def read_transcript(video_id, languages):
    # Public captions only, no authentication bypass. Retrieval may be blocked by YouTube.
    from youtube_transcript_api import YouTubeTranscriptApi
    api = YouTubeTranscriptApi()
    transcript = api.fetch(video_id, languages=languages)
    segments = [{'start':round(s.start,2),'duration':round(s.duration,2),'text':s.text} for s in transcript]
    if not segments: raise RuntimeError('No readable transcript segments')
    return segments


def cached_transcript(out, video_id, languages):
    """Reuse only structurally valid captions for the same language preference order."""
    path = out / 'transcript_cache' / (video_id + '.' + '-'.join(languages) + '.json')
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        segments = data['segments']
        if data['video_id'] != video_id or data['languages'] != languages or not segments:
            return None
        if not all(isinstance(s['text'], str) and isinstance(s['start'], (int, float))
                   and s['start'] >= 0 and isinstance(s['duration'], (int, float))
                   and s['duration'] >= 0 for s in segments):
            return None
        return segments
    except (OSError, ValueError, KeyError, TypeError):
        return None


def cache_transcript(out, video_id, languages, segments):
    directory = out / 'transcript_cache'
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (video_id + '.' + '-'.join(languages) + '.json')
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(dict(video_id=video_id, languages=languages,
                                        segments=segments), ensure_ascii=False), encoding='utf-8')
    temporary.replace(path)


def run_curl(method,url,body=None):
    key=os.getenv('OPENAI_API_KEY')
    if not key: raise RuntimeError('OPENAI_API_KEY missing')
    cmd=['curl','--silent','--show-error','--fail-with-body','--max-time','180','-X',method,
        url, '-H',f'Authorization: Bearer {key}', '-H','OpenAI-Beta: agents=v1', '-H','Content-Type: application/json']
    if os.getenv('OPENAI_PROJECT_ID'):cmd += ['-H',f'OpenAI-Project: {os.getenv("OPENAI_PROJECT_ID")}']
    if body is not None:cmd += ['--data-binary','@-']
    proc=subprocess.run(cmd,input=json.dumps(body) if body is not None else None,text=True,capture_output=True)
    if proc.returncode: raise RuntimeError(f'Agents API HTTP error: {proc.stderr} {proc.stdout[:1000]}')
    return json.loads(proc.stdout)


def extract_text(obj):
    """Find textual assistant output across returned session/item representations."""
    texts=[]
    def visit(o):
        if isinstance(o,dict):
            if o.get('type') in ('output_text','text') and isinstance(o.get('text'),str):texts.append(o['text'])
            if isinstance(o.get('output_text'),str):texts.append(o['output_text'])
            for k,v in o.items():
                if k not in ('text','output_text'):visit(v)
        elif isinstance(o,list):
            for x in o:visit(x)
    visit(obj)
    return '\n'.join(dict.fromkeys(texts))


def parse_observations(raw):
    raw=raw.strip()
    m=re.search(r'```(?:json)?\s*([\s\S]*?)```',raw)
    if m:raw=m.group(1)
    if not raw.startswith(('{','[')):
        start=min([i for i in (raw.find('{'),raw.find('[')) if i>=0],default=-1)
        if start>=0:raw=raw[start:]
    parsed=json.loads(raw)
    if isinstance(parsed,dict):parsed=parsed.get('observations')
    if not isinstance(parsed,list):raise ValueError('Agent did not return observations array')
    return parsed


def agent_extract(video, segments, args):
    prompt = f'''You are a precise automotive evidence analyst. Use ONLY the transcript segments below. Return ONLY JSON {{"observations":[...]}}. No markdown. Each observation must have keys: topic, feedback_type (positive|pain_point|requested_improvement), source_statement, supporting_excerpt, timestamp_seconds, configuration, market_evidence, speaker_type (video_speaker), customer_need_inferred, uncertainties. Evidence must be an exact short substring of ONE supplied segment, and timestamp_seconds must equal its start. Do not invent opinions, market, ownership, or configurations; put null if not established. Do NOT use viewer comments (none provided). Distinguish literal statement from inferred need. Output [] if no relevant customer feedback. Vehicle: {args.vehicle}, generation: {args.generation}, intended research market: {args.market} (NOT proof of video's market). Video: {video['title']} ({video['url']}). Transcript JSON: {json.dumps(segments,ensure_ascii=False)}'''
    body={'agent_id':os.getenv('OPENAI_AGENT_ID','agent_02b849767698466cb1d5dd170487fd25114260ccc4884f4b92'),
          'environment':{'type':'none'},'input':prompt}
    session=run_curl('POST',OPENAI_API,body)
    session_id=session.get('id') or session.get('session_id')
    raw=extract_text(session)
    if session_id and not raw:
        # Nonstreaming sessions can still be running; poll and inspect saved output items.
        for attempt in range(12):
            items=run_curl('GET',f'{OPENAI_API}/{session_id}/items?order=asc&limit=100')
            raw=extract_text(items)
            if raw:break
            time.sleep(5)
    if not raw:raise RuntimeError('Agent session returned no readable output; check session status and required_actions')
    return parse_observations(raw),session_id


def validate_evidence(obs, video, segments, args):
    starts={}
    for segment in segments:
        starts.setdefault(round(segment['start'],2), []).append(segment['text'])
    rows=[]
    for item in obs:
        if not isinstance(item,dict):continue
        try:
            ts=round(float(item['timestamp_seconds']),2)
            excerpt=item['supporting_excerpt']
            if not isinstance(excerpt,str) or not excerpt.strip() or not any(excerpt.strip() in text for text in starts.get(ts, [])):continue
            kind=item.get('feedback_type')
            if kind not in ('positive','pain_point','requested_improvement'):continue
            data={k:item.get(k) for k in FIELDS}
            data.update(video_id=video['video_id'], url=video['url'],title=video['title'], channel=video['channel'],published_at=video['published_at'],vehicle=args.vehicle,generation=args.generation,
                        speaker_type='video_speaker',timestamp_seconds=ts,feedback_type=kind,
                        supporting_excerpt=excerpt.strip())
            rows.append(data)
        except (KeyError,TypeError,ValueError):continue
    return rows


def save(out, videos, evidence, args, errors):
    out.mkdir(parents=True,exist_ok=True)
    (out/'sources.json').write_text(json.dumps(videos,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    with (out/'evidence.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS,extrasaction='ignore');w.writeheader();w.writerows(evidence)
    good=[v for v in videos if v['retrieval_status']=='retrieved']
    topics=Counter((e.get('topic') or 'unspecified',e['feedback_type']) for e in evidence)
    lines=[f'# YouTube customer-feedback research: {args.vehicle} {args.generation}',
        f'',f'Research scope: {args.market}; languages: {", ".join(args.languages)}; publication range: {args.from_date} to {args.to_date}.',
        f'',f'Discovered: {len(videos)}; readable transcripts: {len(good)}; validated observations: {len(evidence)}.',
        '', '## Recurring themes (counts are observations, not independent owners)']
    lines.extend(f'- {topic} — {kind}: {count} observation(s)' for (topic,kind),count in topics.most_common())
    if not topics:lines.append('- None established from retrieved content.')
    lines+=['','## Contradictions and coverage limitations',
            '- Opposing assessments on the same feature must be checked in evidence.json against each video; no automated contradiction claim is made.',
            '- Video speakers are not assumed to be owners. Viewer comments were not accessed.',
            '- Market specificity is not proven by the research filter; individual claims require explicit source evidence.',
            '- Transcript retrieval availability and transcription accuracy vary. Quote validation checks substring matching, not semantic fidelity.',
            '- Search ranks and channel diversity may exclude other relevant perspectives.']
    lines.extend(f'- {v["video_id"]}: {v.get("retrieval_error","unavailable")}' for v in videos if v['selected'] and v['retrieval_status']!='retrieved')
    if errors:lines.extend(['','## Run errors']+[f'- {e}' for e in errors])
    (out/'summary.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


def main(argv=None):
    load_dotenv(Path(__file__).resolve().parent / '.env')
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--vehicle',default='BMW 5 Series');p.add_argument('--generation',default='G60')
    p.add_argument('--market',default='Europe');p.add_argument('--region',default='DE',help='YouTube search region ISO 3166-1 alpha-2; not evidence of market')
    p.add_argument('--languages',nargs='+',default=['en','de']);p.add_argument('--from-date',default='2023-01-01');p.add_argument('--to-date',default=datetime.now(timezone.utc).strftime('%Y-%m-%d'))
    p.add_argument('--max-videos',type=int,default=0,help='Maximum relevant videos to process; 0 processes all (default)')
    p.add_argument('--out',default='output');p.add_argument('--probe-only',action='store_true',help='Stop after the first successfully read video')
    args=p.parse_args(argv)
    if args.max_videos < 0:p.error('--max-videos must be 0 (all) or greater')
    try:
        dates = [datetime.strptime(d,'%Y-%m-%d') for d in (args.from_date,args.to_date)]
    except ValueError:
        p.error('--from-date and --to-date must be valid dates in YYYY-MM-DD format')
    if dates[0] > dates[1]:p.error('--from-date must be on or before --to-date')
    out=Path(args.out);videos=[];evidence=[];errors=[]
    if not os.getenv('YOUTUBE_API_KEY'):
        save(out,videos,evidence,args,['YOUTUBE_API_KEY missing: live discovery not attempted']);print('Missing YOUTUBE_API_KEY. Empty diagnostic artifacts saved.',file=sys.stderr);return 2
    if not os.getenv('OPENAI_API_KEY'):
        save(out,videos,evidence,args,['OPENAI_API_KEY missing: extraction cannot run']);print('Missing OPENAI_API_KEY. Research not started.',file=sys.stderr);return 2
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        save(out,videos,evidence,args,['youtube-transcript-api missing: install requirements.txt']);print('Missing youtube-transcript-api. Install requirements.txt.',file=sys.stderr);return 2
    try:
        args.discovery_checkpoint = lambda found: save(out, found, evidence, args, errors)
        videos=discover(os.environ['YOUTUBE_API_KEY'],args)
        errors.extend(args.discovery_warnings)
        for warning in args.discovery_warnings:
            print(warning, flush=True)
        if not videos and args.discovery_warnings:
            save(out, videos, evidence, args, errors)
            return 3
        selected=select(videos,args)
        save(out,videos,evidence,args,errors)
        if not selected:errors.append('No generation-confirmed candidates found in YouTube metadata')
        transcript_blocked = False
        for video in selected:
            print('Reading',video['url'],flush=True)
            try:
                segments=cached_transcript(out, video['video_id'], args.languages)
                video['transcript_origin'] = 'saved' if segments is not None else 'live'
                if segments is None:
                    if transcript_blocked:
                        video['retrieval_status'] = 'skipped_ip_blocked'
                        video['retrieval_error'] = 'No saved transcript; further requests stopped after YouTube blocked this connection.'
                        save(out, videos, evidence, args, errors)
                        continue
                    segments=read_transcript(video['video_id'],args.languages)
                    cache_transcript(out, video['video_id'], args.languages, segments)
                else:
                    print('Using saved transcript', video['video_id'], flush=True)
                video['retrieval_status']='retrieved';video['transcript_segments']=len(segments)
                (out/'transcripts').mkdir(exist_ok=True)
                (out/'transcripts'/f'{video["video_id"]}.json').write_text(json.dumps(segments,ensure_ascii=False,indent=2),encoding='utf-8')
            except Exception as ex:
                from youtube_transcript_api._errors import IpBlocked, RequestBlocked
                if isinstance(ex, (IpBlocked, RequestBlocked)):
                    transcript_blocked = True
                    message = ('YouTube blocked automated transcript access. Further transcript requests '
                               'are stopped for this run; saved transcripts will still be processed.')
                    errors.append(message)
                    print(message, flush=True)
                video['retrieval_status']='failed';video['retrieval_error']=f'{type(ex).__name__}: {safe_error(ex)[:300]}'
                save(out,videos,evidence,args,errors);continue
            if not os.getenv('OPENAI_API_KEY'):
                video['extraction_status']='skipped_missing_openai_api_key'
            else:
                try:
                    obs,sid=agent_extract(video,segments,args)
                    video['agent_session_id']=sid
                    new=validate_evidence(obs,video,segments,args)
                    video['extraction_status']='completed';video['validated_evidence_count']=len(new)
                    video['discarded_observations']=len(obs)-len(new)
                    evidence.extend(new)
                except Exception as ex:
                    video['extraction_status']='failed';video['extraction_error']=f'{type(ex).__name__}: {safe_error(ex)[:500]}'
            save(out,videos,evidence,args,errors)
            if args.probe_only:break
    except Exception as ex:
        videos = getattr(args, 'discovery_videos', videos)
        errors.append(f'{type(ex).__name__}: {safe_error(ex)[:500]}')
        save(out,videos,evidence,args,errors);print(errors[-1],file=sys.stderr);return 1
    save(out,videos,evidence,args,errors)
    print(f'Saved {len(videos)} sources / {len(evidence)} validated observations to {out}')
    if transcript_blocked:
        return 4
    if not any(v.get('extraction_status') == 'completed' for v in videos):
        errors.append('No video completed transcript retrieval and extraction; research failed. See source statuses.')
        save(out,videos,evidence,args,errors)
        print(errors[-1],file=sys.stderr)
        return 1
    return 0

if __name__=='__main__':sys.exit(main())
