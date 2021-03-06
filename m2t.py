# coding: utf-8

import time
import socket
import struct
from bencode import bencode, bdecode
from random import randint
from threading import Thread, Timer, Lock

BOOTSTRAP_ADDR = ("router.bittorrent.com", 6881)
# BOOTSTRAP_ADDR = ("dht.transmissionbt.com", 6881)


def btih2info_hash(btih):
    info_hash = ''
    for i in range(0, len(btih), 2):
        info_hash += chr(int(btih[i:i + 2], 16))
    return info_hash


def random_bytes(n):
    return ''.join((list(chr(randint(0, 255)) for _ in range(n))))


def random_nid():
    return random_bytes(20)


def random_tid():
    return random_bytes(2)


def random_token():
    return random_bytes(8)


def distance(s1, s2):
    return sum(bin(ord(a) ^ ord(b)).count('1') for a, b in zip(s1, s2))


def create_socket(ip, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind((ip, port))
    return s


class Node:

    def __init__(self, nid, ip, port):
        self.nid = nid
        self.ip = ip
        self.port = port
        self.queried = 0

    def __hash__(self):
        return hash(self.nid)

    def __eq__(self, other):
        return self.nid == other.nid

    def __str__(self):
        self.__repr__()

    def __repr__(self):
        return "node<nid: %s, ip: %s, port: %d, queried: " % (self.nid, self.ip, self.port) + str(self.queried) + ">"


class Peer:

    def __init__(self, ip, port):
        self.addr = (ip, port)
        self.asked = False

    def __hash__(self):
        return hash(self.addr)

    def __eq__(self, other):
        return self.addr == other.addr

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        ip, port = self.addr
        return "peer<ip: %s, port: %d, asked: %s>" % (ip, port, self.asked)


class MsgMaker:

    def __init__(self):
        pass

    def form_krpc_msg(self, y, msg_content, tid=None):
        if not tid:
            tid = random_tid()
        msg = {
            't': tid,
            'y': y
        }
        msg.update(msg_content)
        return msg

    def form_query_get_peers(self, nid, info_hash):
        query = {
            'q': 'get_peers',
            'a': {
                'id': nid,
                'info_hash': info_hash
            }
        }
        return self.form_krpc_msg('q', query)

    def form_response_get_peers(self, nid, tid):
        response = {
            'r': {
                'id': nid,
                'token': random_token(),
                'nodes': ''
            }
        }
        return self.form_krpc_msg('r', response, tid)

    def form_response_announce_peer(self, nid, tid):
        response = {
            'r': {
                'id': nid
            }
        }
        return self.form_krpc_msg('r', response, tid)

    def form_response_ping(self, nid, tid):
        response = {
            'r': {
                'id': nid
            }
        }
        return self.form_krpc_msg('r', response, tid)


class DHTProtocolHandler:

    def __init__(self):
        self.mm = MsgMaker()
        self.s = create_socket("0.0.0.0", 6882)

        self.info_hash = None
        self.nid = random_nid()

        self.nodes_lock = Lock()
        self.nodes = set()

        self.peers_lock = Lock()
        self.peers = set()

        self.tids = list()

    def send_msg(self, msg, dst):
        self.s.sendto(bencode(msg), dst)

    def bootstrap(self):
        if self.nodes == set():
            self.send_get_peers(BOOTSTRAP_ADDR)
            Timer(3, self.bootstrap).start()
        else:
            pass

    def get_torrent(self, info_hash):
        self.info_hash = info_hash
        self.bootstrap()

    def send_get_peers(self, address):
        msg = self.mm.form_query_get_peers(self.nid, self.info_hash)
        self.tids.append(msg['t'])
        self.send_msg(msg, address)

    def recv_msg(self):
        while True:
            try:
                msg_bencode, addr = self.s.recvfrom(65536)
                break
            except Exception:
                pass
        return bdecode(msg_bencode), addr

    def on_query(self, tid, q, addr):
        print('query received: %s' % q)
        if q == 'find_node':
            pass
        elif q == 'get_peers':
            self.on_query_get_peers(tid, addr)
        elif q == 'announce_peer':
            self.on_query_announce_peer(tid, addr)
        elif q == 'ping':
            self.on_query_ping(tid, addr)
        else:
            pass

    def on_query_get_peers(self, tid, addr):
        msg = self.mm.form_response_get_peers(self.nid, tid)
        self.send_msg(msg, addr)

    def on_query_announce_peer(self, tid, addr):
        msg = self.mm.form_response_announce_peer(self.nid, tid)
        self.send_msg(msg, addr)

    def on_query_ping(self, tid, addr):
        msg = self.mm.form_response_ping(self.nid, tid)
        self.send_msg(msg, addr)

    def on_response(self, tid, response):
        if tid in self.tids:
            self.on_response_get_peers(response)
            self.tids.remove(tid)
        else:
            print('tid=%s not exist.' % str(tid))

    def on_response_get_peers(self, response):
        if response.has_key('values'):
            self.decode_peers(response['values'])
        if response.has_key('nodes'):
            self.decode_nodes(response['nodes'])

    def decode_peers(self, peers):
        for peer in peers:
            ip = socket.inet_ntoa(peer[:4])
            port, = struct.unpack('>H', peer[4:])
            self.peers_lock.acquire()
            self.peers.add(Peer(ip, port))
            self.peers_lock.release()

    def decode_nodes(self, nodes):
        for i in range(0, len(nodes), 26):
            nid = nodes[i:i + 20]
            ip = socket.inet_ntoa(nodes[i + 20:i + 24])
            port, = struct.unpack('>H', nodes[i + 24:i + 26])
            node = Node(nid, ip, port)
            self.nodes_lock.acquire()
            self.nodes.add(node)
            self.nodes_lock.release()

    def msg_listener(self):
        while True:
            msg, addr = self.recv_msg()
            try:
                y = msg['y']
                if y == 'q':
                    self.on_query(msg['t'], msg['q'], addr)
                elif y == 'r':
                    self.on_response(msg['t'], msg['r'])
                elif y == 'e':
                    print(msg['e'])
                else:
                    pass
            except:
                print("no dht msg recved -> ", msg)


    def auto_get_peers(self):
        while True:
            send_count = 0
            self.nodes_lock.acquire()
            for node in self.nodes:
                if send_count >= 300:
                    break
                if node.queried < 3:
                    self.send_get_peers((node.ip, node.port))
                    node.queried += 1
                    send_count += 1
            self.nodes_lock.release()
            time.sleep(1)

    def auto_get_metadata(self):
        md = MetadataDownloader()
        while True:
            self.peers_lock.acquire()
            peers = self.peers.copy()
            self.peers_lock.release()
            for peer in peers:
                if peer.asked == True:
                    continue
                print('try to get metadata from (%s, %d)' %peer.addr)
                metadata = md.get_metadata(self.info_hash, peer.addr)
                peer.asked = True
                if metadata != None:
                    # todo metadata got
                    return
            if len(peers) == len(self.peers):
                for peer in peers:
                    peer.asked = False
            time.sleep(1)

    def run(self):
        auto_get_peers_thread = Thread(target=self.auto_get_peers)
        auto_get_metadata_thread = Thread(target=self.auto_get_metadata)
        msg_listener_thread = Thread(target=self.msg_listener)
        auto_get_peers_thread.start()
        auto_get_metadata_thread.start()
        msg_listener_thread.start()


class MetadataDownloader:

    def __init__(self):
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.s.settimeout(5)
        self.peerid = random_nid()
        self.info_hash = None

    def get_metadata(self, info_hash, remote_peer):
        self.info_hash = info_hash
        try:
            self.s.connect(remote_peer)
            print('connect remote peer (%s, %d) succeed.' %remote_peer)
            self.send_peer_handshake()
            msg = self.recv_msg()
            print(msg)
        except:
            print('connect remote peer (%s, %d) error.' %remote_peer)
            self.s.close()
            self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.s.settimeout(5)
            return

    def send_msg(self, msg):
        self.s.send(msg)

    def recv_msg(self):
        return self.s.recv(65535)

    def send_peer_handshake(self):
        msg = ''
        msg += '\x13BitTorrent protocol'
        msg += '\x00\x00\x00\x00\x00\x10\x00\x00'
        msg += info_hash
        msg += self.peerid
        self.send_msg(msg)


if __name__ == "__main__":
    from sys import argv
    if len(argv) != 2:
        print('Only a 40 bytes infohash is required as an argument.')
        exit(0)
    info_hash = btih2info_hash(argv[1])

    dht = DHTProtocolHandler()
    dht.run()
    dht.get_torrent(info_hash)
