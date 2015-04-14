import socket
import random
import threading
import Queue

class RxPConnectionHandler:

    def __init__(self):
        self.state = "CLOSED"
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.address = 0
        self.sendWindow = None
        self.recvWindow = None
        self.messageQueue = Queue.Queue()

    def bind(self, ip_address, port):
        self.address = (ip_address, port)
        self.socket.bind(self.address)
   
    def listen(self, connections):
        if self.state == "CLOSED":
            self.state = "LISTEN"
        self.listeningQueue = Queue.Queue(5)
        self.activeConnections = {}
        receiveThread = threading.Thread(name='receive-messages',
                         target=self.listenMessages)
        receiveThread.setDaemon(True)
        receiveThread.start()

    def accept(self):
        newConnection = self.listeningQueue.get(True)
        self.activeConnections[newConnection.destinationAddress] = newConnection
        SYNrequest = newConnection.messageQueue.get()
        newConnection.processMessage(SYNrequest)
        ACKmessage = newConnection.messageQueue.get()
        newConnection.processMessage(ACKmessage)
        return newConnection

    def connect(self, ip_address, port):
        self.destinationAddress = (ip_address, port)
       
        self.sequenceNumber = random.randint(0, 255)

        synMessage = self.sendSYN(self.sequenceNumber)
        self.resendTimer = threading.Timer(5, self.resendMessage, args=[synMessage])
        self.resendTimer.setDaemon(True)
        self.resendTimer.start()
        self.state = "SYN-SENT"

        while self.state != "ACK-SENT":
            SYNACKmessage, address = self.receiveMessage()
            self.processMessage(SYNACKmessage)
        while self.state != "ESTABLISHED":
            ACKmessage, address = self.receiveMessage()
            self.processMessage(ACKmessage)

    def close(self):
        if self.state == "LISTEN":
            self.state = "CLOSED"
        elif self.state == "SYN-SENT":
            self.state = "CLOSED"
        elif self.state == "ESTABLISHED":
            self.state = "FIN-WAIT-1"

    def resendMessage(self, message):
        self.sendMessage(message)
        self.resendTimer = threading.Timer(5, self.resendMessage, args=[message])
        self.resendTimer.setDaemon(True)
        self.resendTimer.start()

    def receiveMessage(self):
        received, address = self.socket.recvfrom(65507)
        message = bytearray(received)
        rxpMessage = self.parseMessage(message)
        return rxpMessage, address

    def listenMessages(self):
        while True:
            rxpMessage, address = self.receiveMessage()
            if rxpMessage.synFlag and not rxpMessage.ackFlag and address not in self.activeConnections:
                """ New SYN request, queue the connection
                """
                newConnection = RxPConnectionHandler()
                newConnection.socket = self.socket
                newConnection.address = self.address
                newConnection.destinationAddress = address
                newConnection.state = "LISTEN"
                newConnection.messageQueue.put(rxpMessage)
                self.listeningQueue.put(newConnection)
            elif address in self.activeConnections:
                connection = self.activeConnections[address]
                connection.messageQueue.put(rxpMessage)

    def processMessage(self, rxpMessage):
        print "current state:", self.state
        if rxpMessage:
            # opening handshake states
            if self.state == "LISTEN":
                if rxpMessage.isSYN() and rxpMessage.checkIntegrity():
                    self.ackNumber = (rxpMessage.sequenceNumber + 1) % 256
                    self.sequenceNumber = random.randint(0, 255)
                    synackMessage = self.sendSYNACK(self.sequenceNumber, self.ackNumber)
                    self.resendTimer = threading.Timer(5, self.resendMessage, args=[synackMessage])
                    self.resendTimer.setDaemon(True)
                    self.resendTimer.start()
                    self.state = "SYN-RCVD"

            elif self.state == "SYN-RCVD":
                if rxpMessage.isSYNACK() and rxpMessage.checkIntegrity():
                    self.resendTimer.cancel()
                    self.ackNumber = (rxpMessage.sequenceNumber + 1) % 256
                    self.sequenceNumber = (self.sequenceNumber + 1) % 256
                    self.sendACK(self.sequenceNumber, self.ackNumber)
                    self.state = "ESTABLISHED"
                    self.recvWindow = RxPReceiveWindow(5, self.ackNumber, self)
                    self.sendWindow = RxPSendWindow(5, self.sequenceNumber, self)
                elif rxpMessage.finFlag:
                    self.state = "LISTEN"

            elif self.state == "SYN-SENT":
                if rxpMessage.isSYNACK() and rxpMessage.checkIntegrity():
                    self.resendTimer.cancel()
                    self.sequenceNumber = (self.sequenceNumber + 1) % 256
                    self.ackNumber = (rxpMessage.sequenceNumber + 1) % 256
                    synackMessage = self.sendSYNACK(self.sequenceNumber, self.ackNumber)
                    self.resendTimer = threading.Timer(5, self.resendMessage, args=[synackMessage])
                    self.resendTimer.setDaemon(True)
                    self.resendTimer.start()
                    self.state = "ACK-SENT"

            elif self.state == "ACK-SENT":
                if rxpMessage.isACK() and rxpMessage.checkIntegrity():
                    self.resendTimer.cancel()
                    self.sequenceNumber = (self.sequenceNumber + 1) % 256
                    self.ackNumber = (rxpMessage.sequenceNumber + 1) % 256
                    self.state = "ESTABLISHED"
                    self.recvWindow = RxPReceiveWindow(5, self.ackNumber, self)
                    self.sendWindow = RxPSendWindow(5, self.sequenceNumber, self)

            # connection established
            elif self.state == "ESTABLISHED":
                if rxpMessage.finFlag:
                    self.state = "CLOSE_WAIT"
                elif rxpMessage.isACK() or rxpMessage.isNACK():
                    self.sendWindow.receiveMessage(rxpMessage)
                else:
                    self.receiveWindow.receiveMessage(rxpMessage)

            # closing handshake states
            elif self.state == "FIN-WAIT-1":
                if rxpMessage.finFlag and not rxpMessage.ackFlag:
                    self.state = "CLOSING"
                elif rxpMessage.ackFlag and not rxpMessage.finFlag:
                    self.state = "FIN-WAIT-2"
                elif rxpMessage.finFlag and rxpMessage.ackFlag:
                    self.state = "TIMED-WAIT"
            elif self.state == "FIN-WAIT-2":
                if rxpMessage.finFlag:
                    self.state = "TIMED-WAIT"
            elif self.state == "CLOSING":
                if rxpMessage.ackFlag:
                    self.state = "TIMED-WAIT"
            elif self.state == "TIMED-WAIT":
                return
            elif self.state == "CLOSE-WAIT":
                return
            elif self.state == "LAST-ACK":
                if rxpMessage.ackFlag:
                    self.state = "CLOSED"
        print "New state:", self.state

    def bindToTempAddress(self):
        port = 7000
        done = False
        while not done:
            try:
                self.socket.bind((socket.gethostname(), port))
                done = True
            except Exception:
                port += 1
        self.address = (socket.gethostname(), port)

    def sendMessage(self, message):
        return self.socket.sendto(message.generateBytearray(), self.destinationAddress) - 8

    def sendSYN(self, sequenceNumber):
        if not self.address:
            self.bindToTempAddress()

        rxpMessage = RxPMessage()
        rxpMessage.sourcePort = self.address[1]
        rxpMessage.destPort = self.destinationAddress[1] 
        rxpMessage.sequenceNumber = sequenceNumber
        rxpMessage.ackNumber = 0
        rxpMessage.synFlag = True
        rxpMessage.ackFlag = False
        rxpMessage.nackFlag = False 
        rxpMessage.finFlag = False
        self.sendMessage(rxpMessage)
        return rxpMessage

    def sendSYNACK(self, sequenceNumber, ackNumber):
        rxpMessage = RxPMessage()
        rxpMessage.sourcePort = self.address[1]
        rxpMessage.destPort = self.destinationAddress[1] 
        rxpMessage.sequenceNumber = sequenceNumber
        rxpMessage.ackNumber = ackNumber
        rxpMessage.synFlag = True
        rxpMessage.ackFlag = True
        rxpMessage.nackFlag = False 
        rxpMessage.finFlag = False
        self.sendMessage(rxpMessage)
        return rxpMessage

    def sendACK(self, sequenceNumber, ackNumber):
        rxpMessage = RxPMessage()
        rxpMessage.sourcePort = self.address[1]
        rxpMessage.destPort = self.destinationAddress[1] 
        rxpMessage.sequenceNumber = sequenceNumber
        rxpMessage.ackNumber = ackNumber
        rxpMessage.synFlag = False
        rxpMessage.ackFlag = True
        rxpMessage.nackFlag = False 
        rxpMessage.finFlag = False
        self.sendMessage(rxpMessage)
        return rxpMessage

    def sendNACK(self, sequenceNumber, nackNumber):
        rxpMessage = RxPMessage()
        rxpMessage.sourcePort = self.address[1]
        rxpMessage.destPort = self.destinationAddress[1] 
        rxpMessage.sequenceNumber = 0
        rxpMessage.ackNumber = nackNumber
        rxpMessage.synFlag = False
        rxpMessage.ackFlag = False
        rxpMessage.nackFlag = True 
        rxpMessage.finFlag = False
        self.sendMessage(rxpMessage)
        return rxpMessage

    def sendFIN(self, sequenceNumber):
        rxpMessage = RxPMessage()
        rxpMessage.sourcePort = self.address[1]
        rxpMessage.destPort = self.destinationAddress[1] 
        rxpMessage.sequenceNumber = sequenceNumber
        rxpMessage.ackNumber = 0
        rxpMessage.synFlag = False
        rxpMessage.ackFlag = False
        rxpMessage.nackFlag = False
        rxpMessage.finFlag = True
        self.sendMessage(rxpMessage)
        return rxpMessage

    def sendFINACK(self, sequenceNumber, ackNumber):
        rxpMessage = RxPMessage()
        rxpMessage.sourcePort = self.address[1]
        rxpMessage.destPort = self.destinationAddress[1] 
        rxpMessage.sequenceNumber = sequenceNumber
        rxpMessage.ackNumber = ackNumber
        rxpMessage.synFlag = False
        rxpMessage.ackFlag = False
        rxpMessage.nackFlag = True 
        rxpMessage.finFlag = True
        self.sendMessage(rxpMessage)
        return rxpMessage

    def parseMessage(self, message):        
        """ Takes in the message as a bytearray
            Returns an RxPMessage object with the data 
        """
        try:
            rxpMessage = RxPMessage()
            rxpMessage.sourcePort = (message[0] << 8) + message[1]
            rxpMessage.destPort = (message[2] << 8) + message[3]
            rxpMessage.sequenceNumber = message[4]
            rxpMessage.ackNumber = message[5]
            rxpMessage.synFlag = (message[6] & 0b10000000) >> 7
            rxpMessage.ackFlag = (message[6] & 0b01000000) >> 6
            rxpMessage.nackFlag = (message[6] & 0b00100000) >> 5
            rxpMessage.finFlag = (message[6] & 0b00010000) >> 4
            rxpMessage.checksum = message[7]
            rxpMessage.data = message[8:]
            return rxpMessage
        except Exception:
            return None

class RxPMessage:
    def __init__(self):
        self.sourcePort = 0
        self.destPort = 0
        self.sequenceNumber = 0
        self.ackNumber = 0
        self.synFlag = 0
        self.ackFlag = 0
        self.nackFlag = 0
        self.finFlag = 0
        self.checksum = 0
        self.data = bytearray()
        self.acked = False

    def generateBytearray(self):
        """ Generates a bytearray from the message fields
            including calculating the checksum
        """
        message = self.toBytearray()
        message[7] = 0
        checksum = 0
        for byte in message:
            checksum += byte
            checksum = (checksum + (checksum >> 8)) & 0xff
        checksum = (~checksum & 0xff)
        message[7] = checksum
        self.checksum = checksum
        return message

    def toBytearray(self):
        """ Converts the message to a bytearray representation
        """
        message = bytearray()
        message.append(self.sourcePort >> 8)
        message.append(self.sourcePort & 0b11111111)
        message.append(self.destPort >> 8)
        message.append(self.destPort & 0b11111111)
        message.append(self.sequenceNumber)
        message.append(self.ackNumber)
        
        flags = 0
        if self.synFlag:
            flags += 0b10000000
        if self.ackFlag:
            flags += 0b01000000
        if self.nackFlag:
            flags += 0b00100000
        if self.finFlag:
            flags += 0b00010000
        message.append(flags)
        message.append(self.checksum)
        message += self.data
        return message

    def checkIntegrity(self):
        message = self.toBytearray()
        checksum = 0
        for byte in message:
            checksum += byte
            checksum = (checksum + (checksum >> 8)) & 0xff
        checksum = (~checksum & 0xff)
        return checksum == 0

    def isSYN(self):
        return (self.synFlag and not self.ackFlag and not self.nackFlag and not self.finFlag)

    def isSYNACK(self):
        return (self.synFlag and self.ackFlag and not self.nackFlag and not self.finFlag)

    def isACK(self):
        return (not self.synFlag and self.ackFlag and not self.nackFlag and not self.finFlag)

class RxPReceiveWindow:

    def __init__(self, windowSize, sequenceStart, connection):
        self.messageBuffer = [None]*windowSize
        self.windowSize = windowSize
        self.startSequenceNumber = 0
        self.connection = connection

    def receiveMessage(self, message):
        windowIndex = message.sequenceNumber - self.startSequenceNumber

class RxPSendWindow:
    def __init__(self, windowSize, sequenceStart, connection, timeout=10):
        self.messageBuffer = [None]*windowSize
        self.windowSize = windowSize
        self.startSequenceNumber = 0
        self.timeout = timeout
        self.connection = connection

    def addMessage(self, message):
        self.messageBuffer

    def receiveMessage(self, message):
        windowIndex = message.ackNumber - self.startSequenceNumber - 1
        if windowIndex >= 0 and windowIndex < self.windowSize:
            message = self.messageBuffer[windowIndex]
            message.acked = True
            if windowIndex == 0:
                acked = self.popAllACKed()
                ret

    def popAllACKed(self):
        ACKed = []
        lastUnACKed = 0
        done = False
        while not done and lastUnACKed < self.windowSize:
            message = self.messageBuffer[lastUnACKed]
            if message and message.acked:
                lastUnACKed += 1
            else:
                done = True
        ACKed = self.messageBuffer[:lastUnAcked]
        self.messageBuffer = self.messageBuffer[lastUnAcked:]
        if len(self.messageBuffer) < 5:
            self.messageBuffer += [None]*(5 - len(self.messageBuffer))
        return ACKed