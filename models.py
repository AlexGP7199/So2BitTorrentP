import math
import hashlib

from bitstring import BitArray

BLOCK_SIZE = 2**14

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
       
        #handshake = pstrlen+pstr+reserved+str(info_hash)+peer_id
        handshake = pstrlen+pstr+reserved+str(info_hash)+peer_id

        return handshake
        #return bytes(handshake, 'utf-8')

    def set_bit_field(self, payload):
        # TODO: check to see if valid bitfield. Aka the length of the bitfield 
        # matches with the 'on' bits. 
        # COULD BE MALICOUS and you should drop the connection. 
        # Need to calculate the length of the bitfield. otherwise, drop 
        # connection.
        self.bit_field = BitArray(bytes=payload)

    def fileno(self):
        return self.socket.fileno()
    
class Piece(object):
    """
    Holds all the information about the piece of a file. Holds the hash of that 
    piece as well, which is given by the tracker. 

    The Piece class also tracks what blocks are avialable to download.

    The actual data (which are just bytes) is stored in Block class till the 
    very end, where all the data is concatenated together and stored in 
    self.block. This is so that we save memory.

    TODO: Change it so that all the data is not stored in RAM

    self.pieceIndex     -- The index of where this piece lives in the entire 
                           file.
    self.pieceSize      -- Size of this piece. All pieces should have the same 
                           size besides the very last one.
    self.pieceHash      -- Hash of the piece to verify the piece we downloaded.
    self.finished       -- Flag to tell us when the piece is finished 
                           downloaded.
    self.num_blocks     -- The amount of blocks this piece contains. Again, it
                           should all be the same besides the last one.
    self.blockTracker   -- Keeps track of what blocks are still needed to 
                           download. This keeps track of which blocks to request
                           to peers.
    self.blocks         -- The actual block objects that store the data.
    """

    def __init__(self, piece_index, piece_size, piece_hash):
        self.piece_index = piece_index
        self.piece_size = piece_size
        self.piece_hash = piece_hash
        self.finished = False
        self.num_blocks = int(math.ceil(float(piece_size) / BLOCK_SIZE))
        self.block_tracker = BitArray(self.num_blocks)
        self.blocks = [False]*self.num_blocks
        self.blocks_so_far = 0

    def calculate_last_size(self):
        return self.piece_size - ((self.num_blocks - 1) * (BLOCK_SIZE))

    def add_block(self, offset, data):
        if offset == 0:
            index = 0
        else:
            index = offset/BLOCK_SIZE

        if not self.block_tracker[index]:
            self.blocks[index] = data
            self.block_tracker[index] = True
            self.blocks_so_far += 1

        self.finished = all(self.block_tracker)

        # Need to do something here where I send the piece itself    
        if self.finished:
            return self.check_hash()

        return True

    def reset(self):
        """Reset the piece. Used when the data is bad and need to redownload"""
        self.block_tracker = BitArray(self.num_blocks)
        self.finished = False

    def check_hash(self):
        all_data = ''.join(self.blocks)

        hashed_data = hashlib.sha1(all_data).digest()
        if hashed_data == self.piece_hash:
            self.block = all_data
            return True
        else:
            #self.piece.reset()
            self.reset()
            return False