import RxPConnectionHandler

class RxPSocket:
    """ A reliable data transfer protocol socket
    """

    def __init__(self, timeout=5, windowSize = 1):
        """ Creates a socket
            args: timeout - number of seconds before resending messages
                  windowSize - multiply by 4 to get size of the send and receive windows
        """
        self.connectionHandler = None
        self.timeout = timeout
        self.windowSize = windowSize
        return

    def bind(self, ip_address, port):
        """ Binds the socket to the given address
        """
        self.connectionHandler = RxPConnectionHandler.RxPConnectionHandler(self.timeout, self.windowSize)
        self.connectionHandler.bind(ip_address, port)
        return

    def listen(self, connections):
        """ Begins listening for and queueing incoming connection requests
            args: connections - the maximum number of connections to keep in the waiting queue
        """
        self.connectionHandler.listen(connections)
        return

    def accept(self):
        """ Accepts a queue connection request and establishes the connection
            Note: this is a blocking call
            Return: a new socket for the connection and the address of the other end
        """
        newConnection = self.connectionHandler.accept()
        newSocket = RxPSocket()
        newSocket.connectionHandler = newConnection
        return (newSocket, newConnection.destinationAddress)

    def connect(self, ip_address, port):
        """ Attempts to open a connection to the address
            Note: this is a blocking call
        """
        self.connectionHandler = RxPConnectionHandler.RxPConnectionHandler(self.timeout, self.windowSize)
        self.connectionHandler.connect(ip_address, port)

    def send(self, byte_array):
        """ Sends the provided byte array on the connection
            Return: the number of bytes sent
        """
        return self.connectionHandler.send(byte_array)

    def recv(self, buf_size):
        """ Retrieves at maximum buf_size bytes and returns it
            If less than buf_size bytes are in the receiving buffer, the entire buffer is returned
            Return: a byte array of data pulled from the buffer
        """
        return self.connectionHandler.recv(buf_size)

    def close(self):
        """ Closes the connection and notifies the other send to also begin closing
        """
        self.connectionHandler.close()
