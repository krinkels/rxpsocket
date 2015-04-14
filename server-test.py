import RxPSocket
import socket

server = RxPSocket.RxPSocket()
server.bind(socket.gethostname(), 7001)
server.listen(5)
while True:
    connection, address = server.accept()
    data = connection.recv(1000)
    print data
    connection.send('hi!')
    data = connection.recv(1000)
    print data
    connection.send('hi!')
    data = connection.recv(1000)
    print data
    connection.send('hi!')
