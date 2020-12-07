import uuid
import pudb
import math
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
from piece import Piece

class TorrentAnalizer(object):

    def __init__(self, torrent_file):
        self.id = '0987654321098765432-'
        self.peers = []
        self.pieces = deque([])
        self.torrent_tracker = bencode.bdecode(open(torrent_file, 'rb').read())
        bencode_info = bencode.bencode(self.torrent_tracker['info'])
        self.file_hash = hashlib.sha1(bencode_info).digest()
        self.number_pieces = 0
        self.total_length = 0
        self.completed_pieces = 0
        self.current_piece = None
        self.extract_peers()
        #self.create_pieces()

    def create_pieces(self):
        piece_hashes = self.torrent_tracker['info']['pieces']
        piece_length = self.torrent_tracker['info']['piece length']

        if 'files' in self.torrent_tracker['info']:
            files = self.torrent_tracker['info']['files']
            total_length = sum([file['lenght'] for file in files])
            self.number_pieces = int(math.ceil(float(total_length) / piece_length))
        else:
            total_length = self.torrent_tracker['info']['length']
            self.number_pieces = int(math.ceil(float(total_length) / piece_length))

        counter = total_length
        self.total_length = total_length
        for index in range(self.number_pieces):
            if index == self.number_pieces - 1:
                self.pieces.append(Piece(index, counter, piece_hashes[0:20]))
            else:
                self.pieces.append(Piece(index, piece_length, piece_hashes[0:20]))
                counter -= piece_length
                piece_hashes = piece_hashes[20:]
        
        self.current_piece = self.pieces.popleft()

    def chunk_to_six_bytes(self, peer_string):
        """
        Function to covert the string to 6 byte chunks,
        4 bytes for the IP address and 2 for the port.
        """
        for i in range(0, len(peer_string), 6):
            chunk = peer_string[i:i+6]
            if len(chunk) < 6:
                import pudb; pudb.set_trace()
                #pudb.set_trace()
                raise IndexError("Size of the chunk was not six bytes.")
            yield chunk

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

        for data_chunk in self.chunk_to_six_bytes(response):
            ip = []
            port = None

            for index in range(0, 4):
                ip.append(str(data_chunk[index]))
            
            port = data_chunk[4] * 256 + data_chunk[5]
            socket8 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            socket8.setblocking(0)
            ip = '.'.join(ip)
            peer = Peer(ip, port, socket8, self.file_hash, self.id)
            self.peers.append(peer)
        print(len(self.peers))

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
        #except socket.timeout as err:
        except Exception as err:
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
        #print(announce)
        parse = urlparse(announce)
        ip = socket.gethostbyname(parse.hostname)

        if ip == '127.0.0.1':
            return False

        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.settimeout(8)
        connection = (ip, parse.port)
        message, transaction_id, action = self.assemble_message_transaction_action()

        response = self.send_message(connection, udp_socket, message, transaction_id, action, 16)
        connection_id = response[8:]

        message, transaction_id, action = self.make_announce_input(file_hash, connection_id, id.encode())
        response = self.send_message(connection, udp_socket, message, transaction_id, action, 20)
        
        return response[20:]
    
    def is_download_complete(self):
        return self.completed_pieces == self.number_pieces
    
    def find_next_block(self, peer):
        for block_index in range(self.current_piece.num_blocks):
            if not self.current_piece.block_tracker[block_index]:
                if block_index == self.current_piece.num_blocks - 1:
                    size = self.current_piece.calculate_last_size()
                else:
                    size = piece.BLOCK_SIZE
                return (self.current_piece.piece_index, block_index * piece.BLOCK_SIZE, size)
        return None

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
    def __init__(self, ip, port, socket, info_hash, peer_id):
        self.ip = ip
        self.port = port
        self.choked = False
        self.bit_field = None
        self.sent_interested = False
        self.socket = socket
        self.buffer_write = self.make_handshake_message(info_hash, peer_id)
        self.buffer_read = ''
        self.handshake = False

    def make_handshake_message(self, info_hash, peer_id):
        pstrlen = '\x13'
        pstr = 'BitTorrent protocol'
        reserved = '\x00\x00\x00\x00\x00\x00\x00\x00'
       
        handshake = pstrlen+pstr+reserved+str(info_hash)+peer_id
        print(handshake)
        return handshake

    def set_bit_field(self, payload):
        # TODO: check to see if valid bitfield. Aka the length of the bitfield 
        # matches with the 'on' bits. 
        # COULD BE MALICOUS and you should drop the connection. 
        # Need to calculate the length of the bitfield. otherwise, drop 
        # connection.
        self.bit_field = BitArray(bytes=payload)

    def fileno(self):
        return self.socket.fileno()
    