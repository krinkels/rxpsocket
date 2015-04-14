import RxPSocket
import socket

mysocket = RxPSocket.RxPSocket()
mysocket.connect(socket.gethostname(), 6000)
