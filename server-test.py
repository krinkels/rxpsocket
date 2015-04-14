import RxPSocket
import socket

server = RxPSocket.RxPSocket()
server.bind(socket.gethostname(), 7001)
server.listen(5)
server.accept()
