"""Diagnostic: how A2S_RULES answers arrive on this machine, packet by packet.

Temporary: removed once the cause is known.
"""
import socket
import struct
import sys
import time

HEAD = b'\xff\xff\xff\xff'


def rules_trace(ip, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(5)
    out = []
    t = time.time()
    try:
        s.sendto(HEAD + b'V' + HEAD, (ip, port))
        r, _ = s.recvfrom(65535)
        out.append('first %d bytes type %r' % (len(r), r[4:5]))
        if r[4:5] == b'A':
            s.sendto(HEAD + b'V' + r[5:9], (ip, port))
            for _ in range(10):
                try:
                    r, _ = s.recvfrom(65535)
                except socket.timeout:
                    out.append('timeout waiting for more')
                    break
                if r[:4] == b'\xfe\xff\xff\xff':
                    pid, total, number = struct.unpack('<iBB', r[4:10])
                    out.append('split id %d part %d/%d %d bytes' % (pid, number + 1, total, len(r)))
                    if number + 1 >= total:
                        break
                else:
                    out.append('single %d bytes type %r' % (len(r), r[4:5]))
                    break
    except Exception as e:
        out.append('error %s' % e)
    finally:
        s.close()
    return '%s:%d (%dms): %s' % (ip, port, (time.time() - t) * 1000, ' | '.join(out))


def main():
    for a in sys.argv[1:]:
        ip, port = a.rsplit(':', 1)
        print(rules_trace(ip, int(port)))


if __name__ == '__main__':
    main()
