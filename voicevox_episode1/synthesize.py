#!/usr/bin/env python3
import json, re, time, wave, subprocess
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = 'http://127.0.0.1:50021'
ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'output'
OUT.mkdir(exist_ok=True)

SPEAKERS = {
    'narrator': dict(id=31, name='VOICEVOX:No.7（読み聞かせ）', speed=0.94, pitch=-0.02, intonation=0.88, volume=1.00),
    '梓': dict(id=14, name='VOICEVOX:冥鳴ひまり（ノーマル）', speed=1.00, pitch=-0.02, intonation=0.90, volume=1.00),
    '美月': dict(id=48, name='VOICEVOX:ナースロボ＿タイプＴ（ノーマル）', speed=0.98, pitch=0.02, intonation=0.92, volume=1.00),
    '城戸': dict(id=13, name='VOICEVOX:青山龍星（ノーマル）', speed=0.94, pitch=-0.04, intonation=0.82, volume=1.00),
    '若い城戸': dict(id=11, name='VOICEVOX:玄野武宏（ノーマル）', speed=0.97, pitch=-0.02, intonation=0.90, volume=1.00),
    '玲奈': dict(id=9, name='VOICEVOX:波音リツ（ノーマル）', speed=0.96, pitch=-0.03, intonation=0.88, volume=1.00),
    '佐伯': dict(id=53, name='VOICEVOX:雀松朱司（ノーマル）', speed=1.01, pitch=-0.01, intonation=0.93, volume=1.00),
    '高瀬': dict(id=11, name='VOICEVOX:玄野武宏（ノーマル）', speed=0.96, pitch=-0.03, intonation=0.86, volume=1.00),
    '少女': dict(id=46, name='VOICEVOX:小夜/SAYO（ノーマル）', speed=0.92, pitch=0.05, intonation=0.80, volume=0.92),
}

REPLACEMENTS = {
    '白嶺': 'はくれい', '梓': 'あずさ', '美月': 'みづき', '依織': 'いおり',
    '城戸': 'きど', '玲奈': 'れな', '佳代': 'かよ', '佐伯': 'さえき',
    '高瀬': 'たかせ', '河井': 'かわい', '大沢美紀': 'おおさわみき',
    '青葉研究所': 'あおば研究所', 'R-17': 'アールじゅうなな',
    'Wi-Fi': 'ワイファイ', '二十三時四十分': 'にじゅうさんじ、よんじゅっぷん'
}


def reading(text):
    for before, after in sorted(REPLACEMENTS.items(), key=lambda item: -len(item[0])):
        text = text.replace(before, after)
    return text.replace('／', '。').replace('・', '、')


def parse_script():
    raw = (ROOT / 'episode1.txt').read_text(encoding='utf-8')
    segments = []

    def add(role, text, pause=350):
        text = text.strip()
        if not text:
            return
        sp = SPEAKERS[role]
        segments.append({
            'role': role, 'speaker_id': sp['id'], 'speaker_name': sp['name'],
            'text': reading(text), 'speedScale': sp['speed'],
            'pitchScale': sp['pitch'], 'intonationScale': sp['intonation'],
            'volumeScale': sp['volume'], 'pause_ms': pause,
        })

    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith('第1話'):
            add('narrator', '白い部屋の証人。第一話、白い部屋。', 900)
            continue
        if line.startswith('【') and line.endswith('】'):
            inner = line[1:-1]
            match = re.match(r'(\d+)\s*(.*)', inner)
            if match:
                scene = {'1':'第一場。','2':'第二場。','3':'第三場。','4':'第四場。',
                         '5':'第五場。','6':'第六場。','7':'第七場。','8':'第八場。'}
                inner = scene.get(match.group(1), '') + match.group(2)
            add('narrator', inner, 1000)
            continue
        match = re.match(r'^(若い城戸|美月|梓|城戸|玲奈|佐伯|高瀬|女性)「(.*)」$', line)
        if match:
            role = '玲奈' if match.group(1) == '女性' else match.group(1)
            add(role, match.group(2), 260)
            continue
        match = re.match(r'^「(.*)」$', line)
        if match:
            add('少女', match.group(1), 480)
            continue
        pause = 420
        if line in {'白い光。', '青い靴。', '一。', '二。', '三。'}:
            pause = 650
        if line.startswith('『次は') or line.startswith('『先生は'):
            pause = 700
        add('narrator', line, pause)

    merged = []
    for segment in segments:
        if (merged and segment['role'] == 'narrator' and merged[-1]['role'] == 'narrator'
                and merged[-1]['pause_ms'] < 800 and segment['pause_ms'] < 800
                and len(merged[-1]['text']) + len(segment['text']) < 190):
            merged[-1]['text'] += ' ' + segment['text']
            merged[-1]['pause_ms'] = segment['pause_ms']
        else:
            merged.append(segment)
    return merged


def post(path, params=None, payload=None, timeout=240):
    url = BASE + path
    if params:
        url += '?' + urlencode(params)
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode('utf-8')
    headers = {'Content-Type': 'application/json'} if body is not None else {}
    req = Request(url, data=body, headers=headers, method='POST')
    for attempt in range(5):
        try:
            with urlopen(req, timeout=timeout) as response:
                data = response.read()
                if path == '/audio_query':
                    return json.loads(data)
                return data
        except Exception as exc:
            if attempt == 4:
                raise
            print(f'retry {path} {attempt + 1}: {exc}', flush=True)
            time.sleep(2 * (attempt + 1))


def wait_engine():
    for _ in range(240):
        try:
            with urlopen(BASE + '/version', timeout=4) as response:
                print('VOICEVOX ENGINE', response.read().decode('utf-8'), flush=True)
                return
        except Exception:
            time.sleep(2)
    raise RuntimeError('VOICEVOX engine did not start')


def silence(params, milliseconds):
    frames = int(params.framerate * milliseconds / 1000)
    return b'\x00' * frames * params.nchannels * params.sampwidth


def main():
    wait_engine()
    segments = parse_script()
    rendered = []
    manifest = []

    for index, segment in enumerate(segments, 1):
        speaker = segment['speaker_id']
        print(f'[{index:03d}/{len(segments)}] {segment["role"]}: {segment["text"][:55]}', flush=True)
        query = post('/audio_query', {'speaker': speaker, 'text': segment['text']})
        query['speedScale'] = segment['speedScale']
        query['pitchScale'] = segment['pitchScale']
        query['intonationScale'] = segment['intonationScale']
        query['volumeScale'] = segment['volumeScale']
        query['prePhonemeLength'] = 0.06
        query['postPhonemeLength'] = 0.12
        audio = post('/synthesis', {'speaker': speaker}, query)
        wav_path = OUT / f'{index:03d}.wav'
        wav_path.write_bytes(audio)
        rendered.append((wav_path, int(segment['pause_ms'])))
        manifest.append({'index': index, **segment, 'file': wav_path.name})

    combined = OUT / '白い部屋の証人_第1話_VOICEVOX.wav'
    base = None
    with wave.open(str(combined), 'wb') as destination:
        for wav_path, pause_ms in rendered:
            with wave.open(str(wav_path), 'rb') as source:
                params = source.getparams()
                current = (params.nchannels, params.sampwidth, params.framerate)
                if base is None:
                    base = current
                    destination.setnchannels(params.nchannels)
                    destination.setsampwidth(params.sampwidth)
                    destination.setframerate(params.framerate)
                elif current != base:
                    raise RuntimeError(f'WAV format mismatch: {wav_path}')
                destination.writeframes(source.readframes(params.nframes))
                destination.writeframes(silence(params, pause_ms))

    mp3 = OUT / '白い部屋の証人_第1話_VOICEVOX.mp3'
    m4a = OUT / '白い部屋の証人_第1話_VOICEVOX.m4a'
    audio_filter = 'highpass=f=55,loudnorm=I=-16:TP=-1.5:LRA=11'
    subprocess.run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-i', str(combined),
                    '-af', audio_filter, '-ar', '48000', '-b:a', '160k', str(mp3)], check=True)
    subprocess.run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-i', str(combined),
                    '-af', audio_filter, '-ar', '48000', '-c:a', 'aac', '-b:a', '160k', str(m4a)], check=True)
    (OUT / '話者・台詞一覧.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration,size',
                    '-of', 'json', str(mp3)], check=True)
    print('DONE', mp3, mp3.stat().st_size, flush=True)


if __name__ == '__main__':
    main()
