import hashlib
import struct
import math
import sys
import os
import time
import bencode
import requests

from bitstring import BitArray
from torrentAnalizer import TorrentAnalizer
#from piece import pieces
#import logging

#logging = logging.getLogger('bittorrent')

OKBLUE = '\033[94m'
RESET_SEQ = "\033[0m"

HEADER_SIZE = 28 # This is just the pstrlen+pstr+reserved
# TODO make the parser stateless and a parser for each object 

def check_valid_peer(peer, info_hash):
    """
    Check to see if the info hash from the peer matches with the one we have 
    from the .torrent file.
    """
    peer_info_hash = peer.buffer_read[HEADER_SIZE:HEADER_SIZE+len(info_hash)]
    
    if peer_info_hash == info_hash:
        peer.buffer_read = peer.buffer_read[HEADER_SIZE+len(info_hash)+20:]
        peer.handshake = True
        #logging.debug("Handshake Valid")
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
    #logging.debug("Handling Have")
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
    while len(peer.buffer_read) > 3:
        if not peer.handshake:
            if not checkValidPeer(peer, peerMngr.infoHash):
                return False
            elif len(peer.bufferRead) < 4:
                return True

        msgSize = convertBytesToDecimal(peer.bufferRead[0:4], 3)
        if len(peer.bufferRead) == 4:
            if msgSize == '\x00\x00\x00\x00':
                # Keep alive
                return True
            return True 
        
        msgCode = int(ord(peer.bufferRead[4:5]))
        payload = peer.bufferRead[5:4+msgSize]
        if len(payload) < msgSize-1:
            # Message is not complete. Return
            return True
        peer.bufferRead = peer.bufferRead[msgSize+4:]
        if not msgCode:
            # Keep Alive. Keep the connection alive.
            continue
        elif msgCode == 0:
            # Choked
            peer.choked = True
            continue
        elif msgCode == 1:
            # Unchoked! send request
            logging.debug("Unchoked! Finding block")
            peer.choked = False
            pipeRequests(peer, peerMngr)
        elif msgCode == 4:
            handleHave(peer, payload)
        elif msgCode == 5:
            peer.setBitField(payload)
        elif msgCode == 7:
            index = convertBytesToDecimal(payload[0:4], 3)
            offset = convertBytesToDecimal(payload[4:8], 3)
            data = payload[8:]
            if index != peerMngr.curPiece.pieceIndex:

                return True

            piece = peerMngr.curPiece           
            result = piece.addBlock(offset, data)

            if not result:
                logging.debug("Not successful adding block. Disconnecting.")
                return False
            
            if piece.finished:
                peerMngr.numPiecesSoFar += 1
                if peerMngr.numPiecesSoFar < peerMngr.numPieces:
                    peerMngr.curPiece = peerMngr.pieces.popleft()
                shared_mem.put((piece.pieceIndex, piece.blocks))
                logging.info((OKBLUE + "Downloaded piece: %d " + RESET_SEQ) % piece.pieceIndex)
                
            pipeRequests(peer, peerMngr)

        if not peer.sentInterested:
            logging.debug("Bitfield initalized. "
                          "Sending peer we are interested...")
            peer.bufferWrite = makeInterestedMessage()
            peer.sentInterested = True
    return True

def generateMoreData(myBuffer, shared_mem):
    while not shared_mem.empty():
        index, data = shared_mem.get()
        if data:
            myBuffer += ''.join(data)
            yield myBuffer
        else:
            raise ValueError('Pieces was corrupted. Did not download piece properly.')

def writeToMultipleFiles(files, path, peerMngr):
    bufferGenerator = None
    myBuffer = ''
    
    for f in files:
        p = path + '/'.join(f['path'])
        if not os.path.exists(os.path.dirname(p)):
            os.makedirs(os.path.dirname(p))
        with open(p, "w") as fileObj:
            length = f['length']
            if not bufferGenerator:
                bufferGenerator = generateMoreData(myBuffer, peerMngr)

            while length > len(myBuffer):
                myBuffer = next(bufferGenerator)

            fileObj.write(myBuffer[:length])
            myBuffer = myBuffer[length:]

def writeToFile(file, length, peerMngr):
    fileObj = open('./' + file, 'wb')
    myBuffer = ''
   
    bufferGenerator = generateMoreData(myBuffer, peerMngr)

    while length > len(myBuffer):
        myBuffer = next(bufferGenerator)

    fileObj.write(myBuffer[:length])
    fileObj.close()

def write(info, peerMngr):
    if 'files' in info:
        path = './'+ info['name'] + '/'
        writeToMultipleFiles(info['files'], path, peerMngr)    
    else:
        writeToFile(info['name'], info['length'], peerMngr)
