import uuid
#import pudb
import socket
import struct
import random
import hashlib
import bencode
import logging
import requests

from collections import deque
from bitstring import BitArray
from urllib.parse import urlparse

class TorrentAnalizer(object):

    def __init__(self, torrent_file):
        self.id = str(uuid.uuid1())
        self.peers = []
        self.pieces = deque([])
        self.torrent_tracker = bencode.bdecode(open(torrent_file, 'rb').read())
        bencode_info = bencode.bencode(self.torrent_tracker['info'])
        self.file_hash = hashlib.sha1(bencode_info).digest()
        self.extract_peers()

    def chunkToSixBytes(self, peerString):
        """
        Function to covert the string to 6 byte chunks,
        4 bytes for the IP address and 2 for the port.
        """
        # for i in range(0, len(peerString), 6):
        #     chunk = peerString[i:i+6]
        #     if len(chunk) < 6:
        #         import pudb; pudb.set_trace() # <-- aqui eplota!!!!
        #         #pudb.set_trace()
        #         raise IndexError("Size of the chunk was not six bytes.")
        #     yield chunk

    def extract_peers(self):
        announce_list = []

        if 'announce-list' in self.torrent_tracker:
            announce_list = self.torrent_tracker['announce-list']
        else:
            announce_list.append([self.torrent_tracker['announce']])
        
        for announce in announce_list:
            announce = announce[0]

            if announce.startswith('http'):
                piece_length = str(self.torrent_tracker['info']['piece length'])
                response = self.scrape_http(announce, self.file_hash, self.id, piece_length)
            elif announce.startswith('udp'):
                response = self.scrape_udp(announce, self.file_hash, self.id)

            if response:
                break

        print(response)
        # for data_chunk in self.chunkToSixBytes(response):
        #     ip = []
        #     port = None

        #     for index in range(0, 4):
        #         ip.append(str(ord(data_chunk[index])))
            
        #     port = ord(data_chunk[4]) * 256 + ord(data_chunk[5])
        #     socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        #     socket.setblocking(0)
        #     ip = '.'.join(ip)
        #     peer = Peer(ip, port, socket, self.file_hash, self.id)
        #     self.peers.append(peer)
        #     print(self.peers.count)

    def assemble_message_transaction_action(self):
        connection_id = struct.pack('>Q', 0x41727101980)
        action = struct.pack('>I', 0)
        transaction_id = struct.pack('>I', random.randint(0, 100000))

        return (connection_id + action + transaction_id, transaction_id, action)

    def send_message(self, connection, socket, message, transaction_id, action, size):
        print(connection)
        socket.sendto(message, connection)
        # ================================== EL ERROR ES EN ESTA FUNCION ====================================
        try:
            response = socket.recv(2048)
        except socket.timeout as err:
            #print(err)
            #print("Connecting again...")
            logging.debug(err)
            logging.debug("Connecting again...")
            return self.send_message(connection, socket, message, transaction_id, action, size)
        
        if len(response) < size:
            print("Did not get full message. Connecting again...")
            return self.send_message(connection, socket, message, transaction_id, action, size)

        if action != response[0:4] or transaction_id != response[4:8]:
            print("Transaction or Action ID did not match. Trying again...")
            return self.send_message(connection, socket, message, transaction_id, action, size)

        return response

    def make_announce_input(self, info_hash, connection_id, peer_id):
        action = struct.pack('>I', 1)
        transaction_id = struct.pack('>I', random.randint(0, 100000))

        downloaded = struct.pack('>Q', 0)
        left = struct.pack('>Q', 0)
        uploaded = struct.pack('>Q', 0)

        event = struct.pack('>I', 0)
        ip = struct.pack('>I', 0)
        key = struct.pack('>I', 0)
        num_want = struct.pack('>i', -1)
        port = struct.pack('>h', 8000)

        message = (connection_id + action + transaction_id + info_hash + peer_id + downloaded + 
                left + uploaded + event + ip + key + num_want + port)

        return message, transaction_id, action

    def scrape_http(self, announce, file_hash, id, piece_length):
        params = {'info_hash': file_hash,
                  'peer_id': id,
                  'left': piece_length}

        response = requests.get(announce, params=params)

        if response.status_code > 400:
            print('Failed to connect with tracker, status code: {0}, reazon: {1}'.format(response.status_code, response.reason))

        results = bencode.bdecode(response.content)
        return results['peers']

    def scrape_udp(self, announce, file_hash, id):
        print(announce)
        parse = urlparse(announce)
        ip = socket.gethostbyname(parse.hostname)

        if ip == '127.0.0.1':
            return False

        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.settimeout(8)
        connection = (ip, parse.port)
        message, transaction_id, action = self.assemble_message_transaction_action()
        print('first call')
        response = self.send_message(connection, udp_socket, message, transaction_id, action, 16)
        connection_id = response[8:]
        print(connection_id)
        message, transaction_id, action = self.make_announce_input(file_hash, connection_id, id.encode())
        response = self.send_message(connection, udp_socket, message, transaction_id, action, 20)

        return response[20:]

class Peer(object):
    """
    This object contains the information needed about the peer.

    self.ip - The IP address of this peer.
    self.port - Port number for this peer.
    self.choked - sets if the peer is choked or not.
    self.bitField - What pieces the peer has.
    self.socket - Socket object
    self.bufferWrite - Buffer that needs to be sent out to the Peer. When we 
                       instantiate a Peer object, it is automatically filled 
                       with a handshake message.
    self.bufferRead - Buffer that needs to be read and parsed on our end.
    self.handshake - If we sent out a handshake.
    """
    def __init__(self, ip, port, socket, infoHash, peer_id):
        self.ip = ip
        self.port = port
        self.choked = False
        self.bitField = None
        self.sentInterested = False
        self.socket = socket
        self.bufferWrite = self.makeHandshakeMsg(infoHash, peer_id)
        self.bufferRead = ''
        self.handshake = False

    def makeHandshakeMsg(self, infoHash, peer_id):
        pstrlen = '\x13'
        pstr = 'BitTorrent protocol'
        reserved = '\x00\x00\x00\x00\x00\x00\x00\x00'
       
        handshake = pstrlen+pstr+reserved+infoHash+peer_id

        return handshake

    def setBitField(self, payload):
        # TODO: check to see if valid bitfield. Aka the length of the bitfield 
        # matches with the 'on' bits. 
        # COULD BE MALICOUS and you should drop the connection. 
        # Need to calculate the length of the bitfield. otherwise, drop 
        # connection.
        self.bitField = BitArray(bytes=payload)

    def fileno(self):
        return self.socket.fileno()
    