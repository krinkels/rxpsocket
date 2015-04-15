import RxPSocket
import socket
import time

mysocket = RxPSocket.RxPSocket()
mysocket.connect(socket.gethostname(), 7001)
mysocket.send(bytearray('hey!'))
data = mysocket.recv(2048)
print data
mysocket.send(bytearray('hey!'))
data = mysocket.recv(2048)
print data
mysocket.send(bytearray('hey!'))
data = mysocket.recv(2048)
print data
mysocket.close()
