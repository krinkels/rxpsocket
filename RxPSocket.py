import RxPConnectionHandler

class RxPSocket:

    def __init__(self, timeout=5, windowSize = 1):
        self.connectionHandler = None
        self.timeout = timeout
        self.windowSize = windowSize
        return

    def bind(self, ip_address, port):
        self.connectionHandler = RxPConnectionHandler.RxPConnectionHandler(self.timeout, self.windowSize)
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
        self.connectionHandler = RxPConnectionHandler.RxPConnectionHandler(self.timeout, self.windowSize)
        self.connectionHandler.connect(ip_address, port)

    def send(self, byte_array):
        return self.connectionHandler.send(byte_array)

    def recv(self, buf_size):
        return self.connectionHandler.recv(buf_size)

    def close(self):
        self.connectionHandler.close()
