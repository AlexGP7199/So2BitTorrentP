import os
import queue
import argparse
from client_core import ClientCore
from torrent_analizer import TorrentAnalizer

# Parser for the arguments
parser = argparse.ArgumentParser()

# List of arguments
parser.add_argument('torrent_file', type=str)
arguments = parser.parse_args()

print(f'\nThe file to be open is: {arguments.torrent_file}')

# Get torrent file
source_folder = os.path.dirname(os.path.abspath(__file__))
torrent_file_path = os.path.join(source_folder, arguments.torrent_file)
file_analizer = TorrentAnalizer(torrent_file_path)
shared_memory = queue.PriorityQueue()
client = ClientCore(1, "Thread-1", file_analizer, shared_memory, debug=True)
client.run()
