import RxPConnectionHandler

class RxPSocket:

    def __init__(self):
        self.connectionHandler = None
        return

    def bind(self, ip_address, port):
        self.connectionHandler = RxPConnectionHandler.RxPConnectionHandler()
        self.connectionHandler.bind(ip_address, port)
        return

    def listen(self, connections):
        self.connectionHandler.listen(connections)
        return

    def accept(self):
        newConnection = self.connectionHandler.accept()
        newSocket = RxPSocket()
        newSocket.connectionHandler = newConnection
        return (newSocket, newConnection.destinationAddress)

    def connect(self, ip_address, port):
        self.connectionHandler = RxPConnectionHandler.RxPConnectionHandler()
        self.connectionHandler.connect(ip_address, port)

    def send(self, byte_array):
        return self.connectionHandler.send(byte_array)

    def recv(self, buf_size):
        return self.connectionHandler.recv(buf_size)

    def close(self):
        self.connectionHandler.close()
