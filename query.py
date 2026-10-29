"""Reads the map and details every listed Rust server publishes about itself.

badgyver.com lists Rust servers, but its host cannot send the game's UDP
queries. This script runs on GitHub Actions instead: it takes the list of
servers the site publishes (copied to media.badgyver.com), asks each one for
its rules (Valve's A2S_RULES), and writes what changes only with a wipe to
data/servers.json: the map picture Facepunch hosts for the server, the map
seed and size, the map download, the server's own description, header image
and website. The site reads that file from this public repository.

Only the Python standard library is used.
"""
import json
import os
import re
import socket
import struct
import sys
import time
import urllib.request

# The site's list of servers, passed on through R2 by the site's Cloudflare
# Worker: the site's host does not answer GitHub's machines.
TARGETS = 'https://media.badgyver.com/_state/rust-targets.json'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'servers.json')
HEAD = b'\xff\xff\xff\xff'
TIMEOUT = 3.0


def targets():
    req = urllib.request.Request(TARGETS + '?t=' + str(int(time.time())), headers={'User-Agent': 'badgyver-rust-servers-query'})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.load(r)
    if not isinstance(data, dict) or data.get('ok') is not True:
        raise RuntimeError('the target list is not the expected shape')
    return [t for t in data.get('servers', []) if isinstance(t, dict) and t.get('ip') and t.get('qport')]


def receive(sock):
    """One answer, joining split packets (Source format) when the rules are long."""
    first, _ = sock.recvfrom(4096)
    if first[:4] == HEAD:
        return first[4:]
    if first[:4] != b'\xfe\xff\xff\xff':
        raise ValueError('unknown packet')
    parts = {}
    total = None
    packet = first
    while True:
        _, total, number = struct.unpack('<iBB', packet[4:10])
        # Steam splits carry a 2-byte size after the number.
        parts[number] = packet[12:]
        if len(parts) >= total:
            break
        packet, _ = sock.recvfrom(4096)
    data = b''.join(parts[i] for i in range(total))
    return data[4:] if data[:4] == HEAD else data


def rules(ip, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(TIMEOUT)
    try:
        challenge = HEAD
        for _ in range(3):
            sock.sendto(HEAD + b'V' + challenge, (ip, port))
            data = receive(sock)
            if data[:1] == b'A':
                challenge = data[1:5]
                continue
            if data[:1] == b'E':
                count = struct.unpack('<H', data[1:3])[0]
                items = data[3:].split(b'\x00')
                out = {}
                # Values stay bytes: Rust cuts the description into 100-byte
                # chunks, which can split a character between two of them.
                for i in range(0, min(len(items) - 1, count * 2), 2):
                    out[items[i].decode('utf-8', 'replace')] = items[i + 1]
                return out
            break
    finally:
        sock.close()
    return None


def text(b):
    """UTF-8, or the Windows code page some servers still write their text in."""
    try:
        return b.decode('utf-8')
    except UnicodeDecodeError:
        return b.decode('cp1252', 'replace')


def map_image(value):
    """
    The map picture Facepunch hosts for the server. Steam cuts rule values at
    160 characters, which drops the end of this address; the end is always
    "_" + the first 32 characters of its folder + ".jpg" (as the game server
    logs it), so it is put back and checked.
    """
    value = value.strip()
    m = re.match(r'^https://files\.facepunch\.com/rust/map-images/([0-9a-f]{64})/[^/]+$', value)
    if not m:
        return ''
    url = value if value.endswith('.jpg') else value.rsplit('_', 1)[0] + '_' + m.group(1)[:32] + '.jpg'
    try:
        req = urllib.request.Request(url, method='HEAD', headers={'User-Agent': 'badgyver-rust-servers-query'})
        with urllib.request.urlopen(req, timeout=15) as r:
            return url if r.status == 200 and r.headers.get('Content-Type', '').startswith('image/') else ''
    except Exception:
        return ''


def clean(raw):
    desc = text(b''.join(raw.get('description_%02d' % i, b'') for i in range(16))).strip()
    rules_ = {k: text(v) for k, v in raw.items() if not k.startswith('description_')}
    # Rust writes line breaks in the description as a literal backslash-n.
    desc = desc.replace(chr(92) + 'n', '\n').replace(chr(92) + 't', ' ')

    def num(key):
        try:
            return int(float(rules_.get(key, '0') or 0))
        except ValueError:
            return 0

    return {
        'seed': num('world.seed'),
        'size': num('world.size'),
        'map_image': map_image(rules_.get('map_image_url', '')),
        'level_url': rules_.get('level_url', '').strip(),
        'description': desc[:3000],
        'header': rules_.get('headerimage', '').strip(),
        'logo': rules_.get('logoimage', '').strip(),
        'url': rules_.get('url', '').strip(),
    }


def main():
    try:
        old = json.load(open(OUT, encoding='utf-8'))
    except (OSError, ValueError):
        old = {}
    servers = dict(old.get('servers', {}))
    try:
        listed = targets()
    except Exception as e:  # The site is down: keep the last file as it is.
        print('target list unavailable:', e)
        return 0
    wanted = set()
    for t in listed:
        key = '%s:%d' % (t['ip'], int(t['qport']))
        wanted.add(key)
        try:
            r = rules(t['ip'], int(t['qport']))
        except (OSError, ValueError, struct.error) as e:
            print(key, 'no answer:', e)
            r = None
        if r is None:
            continue  # Keep what was read last time.
        servers[key] = clean(r)
        print(key, 'ok, seed', servers[key]['seed'], 'size', servers[key]['size'])
    # Servers no longer listed leave the file.
    servers = {k: v for k, v in servers.items() if k in wanted}
    # The month is written so the file changes at least once a month: GitHub
    # pauses scheduled workflows in repositories with no activity for 60 days.
    new = {'month': time.strftime('%Y-%m', time.gmtime()), 'servers': dict(sorted(servers.items()))}
    if new != old:
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        with open(OUT, 'w', encoding='utf-8', newline='\n') as f:
            json.dump(new, f, ensure_ascii=False, indent=1, sort_keys=True)
            f.write('\n')
        print('written', len(servers), 'servers')
    else:
        print('no change')
    return 0


if __name__ == '__main__':
    sys.exit(main())
