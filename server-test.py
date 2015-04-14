from RxPSocket import *

server = RxPSocket()
server.bind(socket.gethostname(), 6000)
server.listen(5)
server.accept()
