import RxPSocket
import socket

server = RxPSocket.RxPSocket()
server.bind(socket.gethostname(), 6000)
server.listen(5)
server.accept()
