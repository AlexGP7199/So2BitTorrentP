import os
import queue
import argparse
from torrentAnalizer import TorrentAnalizer
from client_core import ClientCore
#from bencoded import bdecode

# Parser for the arguments
parser = argparse.ArgumentParser()

# List of arguments
parser.add_argument('torrent_file', type=str)

arguments = parser.parse_args()

print(f'\nThe file to be open is: {arguments.torrent_file}')


# Get torrent file
source_folder = os.path.dirname(os.path.abspath(__file__))
torrent_file_path = os.path.join(source_folder, arguments.torrent_file)
torrent_analizer = TorrentAnalizer(torrent_file_path)
shared_memory = queue.PriorityQueue()
client = ClientCore(1, "Thread-1", torrent_analizer, shared_memory, debug=True)
client.run()






#torrent_file = bencode.bdecode(open(os.path.join(source_folder, 'big-buck-bunny.torrent'), 'rb').read())

#print(bencode.bencode(torrent_file['info']))
#print(bencode.bencode(torrent_file))
#print(bencode.bencode(torrent_file['creation date']))
#print(torrent_file['creation date'])
#print(torrent_file['info']['name'])
#print(torrent_file['info']['pieces'])
#print(bencode.bencode(torrent_file['info']['pieces']))


#list_test = torrent_file['announce-list']
#for item in list_test:
#    print(item)
