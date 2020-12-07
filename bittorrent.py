import os
import sys
import math
import time
import struct
import hashlib
import bencode
import logging
import requests

from bitstring import BitArray
from torrentAnalizer import TorrentAnalizer

logging = logging.getLogger('bittorrent')

OKBLUE = '\033[94m'
RESET_SEQ = "\033[0m"

HEADER_SIZE = 28 # This is just the pstrlen+pstr+reserved
# TODO make the parser stateless and a parser for each object 

def check_valid_peer(peer, info_hash):
    """
    Check to see if the info hash from the peer matches with the one we have 
    from the .torrent file.
    """
    print('peer info hash')
    print(peer.buffer_read[HEADER_SIZE:HEADER_SIZE+len(info_hash)])
    print('info hash')
    print(info_hash)

    peer_info_hash = peer.buffer_read[HEADER_SIZE:HEADER_SIZE+len(info_hash)]
    
    if peer_info_hash == info_hash:
        peer.buffer_read = peer.buffer_read[HEADER_SIZE+len(info_hash)+20:]
        peer.handshake = True
        logging.debug("Handshake Valid")
        return True
    else:
        return False

def convert_bytes_to_decimal(header_bytes, power):
    size = 0
    for ch in header_bytes:
        size += int(ord(ch))*256**power
        power -= 1
    return size

def handle_have(peer, payload):
    index = convert_bytes_to_decimal(payload, 3)
    logging.debug("Handling Have")
    peer.bit_field[index] = True

def make_interested_message():
    interested = '\x00\x00\x00\x01\x02'
    return interested

def send_request(index, offset, length):
    header = struct.pack('>I', 13)
    id = '\x06'
    index = struct.pack('>I', index)
    offset = struct.pack('>I', offset)
    length = struct.pack('>I', length)
    request = header + id + index + offset + length
    return request

def pipe_requests(peer, torrent_analizer):
    if len(peer.buffer_write) > 0:
        return True

    for x in range(10):
        next_block = torrent_analizer.find_next_block(peer)
        if not next_block:
            return 

        index, offset, length = next_block
        peer.buffer_write = send_request(index, offset, length)
        
def process_message(peer, torrent_analizer, shared_memory):
    #print(len(peer.buffer_read))
    #import pdb; pdb.set_trace()
    while len(peer.buffer_read) > 3:
        
        if not peer.handshake:
            #print('not handshake')
            if not check_valid_peer(peer, torrent_analizer.file_hash):
                print('false')
                return False
            elif len(peer.buffer_read) < 4:
                print('true')
                return True
        
        message_size = convert_bytes_to_decimal(peer.buffer_read[0:4], 3)
        if len(peer.buffer_read) == 4:
            if message_size == '\x00\x00\x00\x00':
                # Keep alive
                return True
            return True 
        
        message_code = int(ord(peer.buffer_read[4:5]))
        payload = peer.buffer_read[5:4 + message_size]
        if len(payload) < message_size - 1:
            # Message is not complete. Return
            return True
        peer.buffer_read = peer.buffer_read[message_size + 4:]
        if not message_code:
            # Keep Alive. Keep the connection alive.
            continue
        elif message_code == 0:
            # Choked
            peer.choked = True
            continue
        elif message_code == 1:
            # Unchoked! send request
            logging.debug("Unchoked! Finding block")
            peer.choked = False
            pipe_requests(peer, torrent_analizer)
        elif message_code == 4:
            handle_have(peer, payload)
        elif message_code == 5:
            peer.set_bit_field(payload)
        elif message_code == 7:
            index = convert_bytes_to_decimal(payload[0:4], 3)
            offset = convert_bytes_to_decimal(payload[4:8], 3)
            data = payload[8:]
            if index != torrent_analizer.current_piece.pieceIndex:

                return True

            piece = torrent_analizer.current_piece           
            result = piece.add_block(offset, data)

            if not result:
                logging.debug("Not successful adding block. Disconnecting.")
                return False
            
            if piece.finished:
                torrent_analizer.completed_pieces += 1
                if torrent_analizer.completed_pieces < torrent_analizer.number_pieces:
                    torrent_analizer.current_piece = torrent_analizer.pieces.popleft()
                shared_memory.put((piece.piece_index, piece.blocks))
                logging.info((OKBLUE + "Downloaded piece: %d " + RESET_SEQ) % piece.pieceIndex)

            pipe_requests(peer, torrent_analizer)

        if not peer.sent_interested:
            #logging.debug("Bitfield initalized. "
                          #"Sending peer we are interested...")
            peer.buffer_write = make_interested_message()
            peer.sent_interested = True
    return True

def generate_more_data(my_buffer, shared_memory):
    while not shared_memory.empty():
        index, data = shared_memory.get()
        if data:
            my_buffer += ''.join(data)
            yield my_buffer
        else:
            raise ValueError('Pieces was corrupted. Did not download piece properly.')

def write_to_multiple_files(files, path, torrent_analizer):
    buffer_generator = None
    my_buffer = ''
    
    for file in files:
        p = path + '/'.join(file['path'])
        if not os.path.exists(os.path.dirname(p)):
            os.makedirs(os.path.dirname(p))
        with open(p, "w") as file_object:
            length = file['length']
            if not buffer_generator:
                buffer_generator = generate_more_data(my_buffer, torrent_analizer)

            while length > len(my_buffer):
                my_buffer = next(buffer_generator)

            file_object.write(my_buffer[:length])
            my_buffer = my_buffer[length:]

def write_to_file(file, length, torrent_analizer):
    file_object = open('./' + file, 'wb')
    my_buffer = ''
   
    buffer_generator = generate_more_data(my_buffer, torrent_analizer)

    while length > len(my_buffer):
        my_buffer = next(buffer_generator)

    file_object.write(my_buffer[:length])
    file_object.close()

def write(info, torrent_analizer):
    if 'files' in info:
        path = './'+ info['name'] + '/'
        write_to_multiple_files(info['files'], path, torrent_analizer)    
    else:
        write_to_file(info['name'], info['length'], torrent_analizer)
