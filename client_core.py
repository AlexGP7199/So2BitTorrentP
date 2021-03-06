import socket
import select
import sys
import multiprocessing
import logging

#import bittorrent
from torrentAnalizer import TorrentAnalizer

class ClientCore(multiprocessing.Process):
    """ 
    This is our event loop that makes our program asynchronous. The program
    keeps looping until the file is fully downloaded.
    """
    def __init__(self, thread_id, name, torrent_analizer, shared_memory, debug=False, info=True):
        multiprocessing.Process.__init__(self)
        self.thread_id = thread_id
        self.name = name
        self.shared_memory = shared_memory
        # if debug:
        #     logging.basicConfig(level=logging.DEBUG)
        # elif info:
        #     logging.basicConfig(level=logging.INFO)
        self.torrent_analizer = torrent_analizer
    
    def connect(self):
        for peer in self.torrent_analizer.peers:
            try:
                peer.socket.connect((peer.ip, peer.port))
            except socket.error:
                # We are going to ignore the error, since we are turing blocking
                # off. Since we are returning before connect can return a 
                # message, it will throw an error. 
                pass

    def remove_peer(self, peer):
        if peer in self.torrent_analizer.peers:
            self.torrent_analizer.peers.remove(peer)

    def run(self):
        self.connect()
        while not self.torrent_analizer.is_download_complete():
            write = [x for x in self.torrent_analizer.peers if x.buffer_write != '']
            read = self.torrent_analizer.peers[:]
            read_list, write_list, error = select.select(read, write, [])
            
            for peer in write_list:
                send_message = peer.buffer_write
                try:
                    peer.socket.send(send_message)
                except socket.error as error:
                    logging.debug(error)
                    self.remove_peer(peer)
                    continue 
                peer.buffer_write = ''

            for peer in read_list:
                try:
                    peer.buffer_read += peer.socket.recv(1028)
                except socket.error as error:
                    logging.debug(error)
                    self.remove_peer(peer)
                    continue
                result = bittorrent.process_message(peer, self.peerMngr, self.shared_mem)
                if not result:
                    # Something went wrong with peer. Discconnect
                    peer.socket.close()
                    self.removePeer(peer)

            if len(self.peerMngr.peers) <= 0:
                raise Exception("NO MORE PEERS")
        bittorrent.write(self.peerMngr.tracker['info'], self.shared_mem)