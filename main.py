import os
import bencode
#from bencoded import bdecode

# open torrent file
source_folder = os.path.dirname(os.path.abspath(__file__))
torrent_file = bencode.bdecode(open(os.path.join(source_folder, 'big-buck-bunny.torrent'), 'rb').read())

#print(bencode.bencode(torrent_file['info']))
#print(bencode.bencode(torrent_file))
#print(bencode.bencode(torrent_file['creation date']))
#print(torrent_file['creation date'])
print(torrent_file['info']['name'])
#print(torrent_file['info']['pieces'])
print(bencode.bencode(torrent_file['info']['pieces']))


#list_test = torrent_file['announce-list']
#for item in list_test:
#    print(item)
