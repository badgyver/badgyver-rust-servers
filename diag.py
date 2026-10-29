"""Diagnostic: which UDP answers reach this machine.

1. A DNS question to 1.1.1.1 (is outbound UDP open at all?).
2. A2S_INFO to Rust servers on their query ports, with and without the
   challenge, to see which ones answer and how.
Prints one line per test. Temporary: removed once the cause is known.
"""
import socket
import struct
import sys
import time

HEAD = b'\xff\xff\xff\xff'
INFO = HEAD + b'TSource Engine Query\x00'


def dns():
    q = struct.pack('>6H', 0x1234, 0x0100, 1, 0, 0, 0) + b'\x07example\x03com\x00' + struct.pack('>2H', 1, 1)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(3)
    try:
        s.sendto(q, ('1.1.1.1', 53))
        r, _ = s.recvfrom(512)
        return 'dns 1.1.1.1:53 -> %d bytes' % len(r)
    except Exception as e:
        return 'dns 1.1.1.1:53 -> %s' % e
    finally:
        s.close()


def a2s(ip, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(4)
    t = time.time()
    try:
        s.sendto(INFO, (ip, port))
        r, _ = s.recvfrom(4096)
        kind = chr(r[4]) if len(r) > 4 else '?'
        if kind == 'A':
            s.sendto(INFO + r[5:9], (ip, port))
            r, _ = s.recvfrom(4096)
            kind = 'A then ' + (chr(r[4]) if len(r) > 4 else '?')
        name = r[6:60].split(b'\x00')[0].decode('utf-8', 'replace')
        return '%s:%d -> %s %d bytes %dms %s' % (ip, port, kind, len(r), (time.time() - t) * 1000, name)
    except Exception as e:
        return '%s:%d -> %s' % (ip, port, e)
    finally:
        s.close()


def main():
    print(dns())
    for a in sys.argv[1:]:
        ip, port = a.rsplit(':', 1)
        print(a2s(ip, int(port)))


if __name__ == '__main__':
    main()
