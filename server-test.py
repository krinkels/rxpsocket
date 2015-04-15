import RxPSocket
import socket
import time

server = RxPSocket.RxPSocket()
server.bind(socket.gethostname(), 7001)
server.listen(5)
connection, address = server.accept()
print "CONNECTION ACCEPTED"
data = connection.recv(1000)
print data
connection.send('hi!')
data = connection.recv(1000)
print data
connection.send('hi!')
data = connection.recv(1000)
print data
connection.send('hi!')
time.sleep(5)
server.close()
