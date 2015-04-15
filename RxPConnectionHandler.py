import socket
import random
import threading
import Queue
import time

class RxPConnectionHandler:

    def __init__(self, timeout=5):
        self.state = "CLOSED"
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.address = 0
        self.sendWindow = None
        self.recvWindow = None
        self.messageQueue = Queue.Queue()
        self.establishLock = threading.Event()
        self.parentConnection = None
        self.timeout = timeout
        self.closeLock = threading.Event()
        self.listeningFlag = threading.Event()

    def bind(self, ip_address, port):
        self.address = (ip_address, port)
        self.socket.bind(self.address)

    def listen(self, connections):
        if self.state == "CLOSED":
            self.setState("LISTEN")
        self.listeningQueue = Queue.Queue(5)
        self.activeConnections = {}
        receiveThread = threading.Thread(name='receive-messages',
                         target=self.listenMessages)
        self.receiveThread.setDomain(True)
        receiveThread.start()

    def accept(self):
        newConnection = self.listeningQueue.get(True)
        self.activeConnections[newConnection.destinationAddress] = newConnection
        message = newConnection.messageQueue.get()
        newConnection.processMessage(message)
        newConnection.establishLock.wait()
        return newConnection

    def connect(self, ip_address, port):
        self.destinationAddress = (ip_address, port)
        self.activeConnections = None 
        self.sequenceNumber = random.randint(0, 255)

        synMessage = self.sendSYN(self.sequenceNumber)
        self.resendTimer = threading.Timer(self.timeout, self.resendMessage, args=[synMessage])
        self.resendTimer.setDaemon(True)
        self.resendTimer.start()
        self.setState("SYN-SENT")

        self.receiveThread = threading.Thread(name='receive-messages',
                         target=self.listenMessages)
        self.receiveThread.setDaemon(True)
        self.receiveThread.start()

        self.establishLock.wait()         

    def send(self, data):
        while len(data) > 0:
            toSendLength = min(len(data), 1000)
            toSend = data[:toSendLength]
            message = self.generateSkeletonMessage()
            message.sequenceNumber = self.sequenceNumber
            message.data = toSend
            self.sendWindow.addMessage(message)
            self.sequenceNumber = (self.sequenceNumber + 1) % 256
            data = data[toSendLength:]
        return len(data)

    def recv(self, bufSize):
        data = self.recvWindow.popData(bufSize)
        return data

    def close(self):
        if self.state == "LISTEN":
            self.setState("CLOSED")
            self.closeLock.wait()
        elif self.state == "SYN-SENT":
            self.sendFIN(self.sequenceNumber, 0)
            self.setState("CLOSED")
            self.closeLock.wait()
        elif self.state == "ESTABLISHED":
            FINmessage = self.generateSkeletonMessage()
            FINmessage.finFlag = True
            FINmessage.sequenceNumber = self.sequenceNumber
            self.sequenceNumber = (self.sequenceNumber + 1) % 256
            self.sendWindow.addMessage(FINmessage)
            self.closeLock.wait()
        elif self.state == "CLOSE-WAIT":
            FINmessage = self.generateSkeletonMessage()
            FINmessage.finFlag = True
            FINmessage.sequenceNumber = self.sequenceNumber
            self.sequenceNumber = (self.sequenceNumber + 1) % 256
            self.sendWindow.addMessage(FINmessage)
            self.closeLock.wait()

    def resendMessage(self, message):
        self.sendMessage(message)
        self.resendTimer = threading.Timer(self.timeout, self.resendMessage, args=[message])
        self.resendTimer.setDaemon(True)
        self.resendTimer.start()

    def receiveMessage(self):
        received, address = self.socket.recvfrom(65535)
        message = bytearray(received)
        rxpMessage = self.parseMessage(message)
        return rxpMessage, address

    def listenMessages(self):
        while not self.listeningFlag.isSet():
            rxpMessage, address = self.receiveMessage()
            if rxpMessage is not None:
                if self.activeConnections is None:
                    self.processMessage(rxpMessage)
                else:
                    if rxpMessage.isSYN() and address not in self.activeConnections:
                        """ New SYN request, queue the connection
                        """
                        ##print "Establishing new connection with", address
                        newConnection = RxPConnectionHandler()
                        newConnection.socket = self.socket
                        newConnection.address = self.address
                        newConnection.destinationAddress = address
                        newConnection.setState("LISTEN")
                        newConnection.parentConnection = self
                        newConnection.messageQueue.put(rxpMessage)
                        newConnection.timeout = self.timeout
                        self.listeningQueue.put(newConnection)
                    elif address in self.activeConnections:
                        connection = self.activeConnections[address]
                        if rxpMessage.isSYN():
                            connection.setState("LISTEN")
                        receiveThread = threading.Thread(name='process-messages',
                                         target=connection.processMessage, args=[rxpMessage])
                        receiveThread.start()

    def processMessage(self, rxpMessage):
        ##print "current state:", self.state
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
                    self.setState("SYN-RCVD")

            elif self.state == "SYN-RCVD":
                if rxpMessage.isSYNACK() and rxpMessage.checkIntegrity():
                    self.resendTimer.cancel()
                    self.ackNumber = (rxpMessage.sequenceNumber + 1) % 256
                    self.sequenceNumber = (self.sequenceNumber + 1) % 256
                    self.sendACK(self.sequenceNumber, self.ackNumber)
                    self.setState("ESTABLISHED")
                    self.establishLock.set()
                    self.recvWindow = RxPReceiveWindow(5, self.ackNumber, self)
                    self.sendWindow = RxPSendWindow(5, self.sequenceNumber, self)
                elif rxpMessage.finFlag:
                    self.setState("LISTEN")

            elif self.state == "SYN-SENT":
                if rxpMessage.isSYNACK() and rxpMessage.checkIntegrity():
                    self.resendTimer.cancel()
                    self.sequenceNumber = (self.sequenceNumber + 1) % 256
                    self.ackNumber = (rxpMessage.sequenceNumber + 1) % 256
                    synackMessage = self.sendSYNACK(self.sequenceNumber, self.ackNumber)
                    self.resendTimer = threading.Timer(5, self.resendMessage, args=[synackMessage])
                    self.resendTimer.setDaemon(True)
                    self.resendTimer.start()
                    self.setState("ACK-SENT")

            elif self.state == "ACK-SENT":
                if rxpMessage.isACK() and rxpMessage.checkIntegrity():
                    self.resendTimer.cancel()
                    self.closeTimer.cancel()
                    self.sequenceNumber = (self.sequenceNumber + 1) % 256
                    self.ackNumber = (rxpMessage.sequenceNumber) % 256
                    self.setState("ESTABLISHED")
                    self.establishLock.set()
                    self.recvWindow = RxPReceiveWindow(5, self.ackNumber, self)
                    self.sendWindow = RxPSendWindow(5, self.sequenceNumber, self)
                elif rxpMessage.checkIntegrity():
                    self.resendTimer.cancel()
                    self.closeTimer.cancel()
                    self.sequenceNumber = (self.sequenceNumber + 1) % 256
                    self.ackNumber = (rxpMessage.sequenceNumber + 1) % 256
                    self.setState("ESTABLISHED")
                    self.establishLock.set()
                    self.recvWindow = RxPReceiveWindow(5, self.ackNumber, self)
                    self.sendWindow = RxPSendWindow(5, self.sequenceNumber, self)
                    self.recvWindow.receiveMessage(rxpMessage) 

            # connection established
            else:
                if rxpMessage.isACK() or rxpMessage.isNACK():
                    self.sendWindow.receiveMessage(rxpMessage)
                else:
                    self.recvWindow.receiveMessage(rxpMessage)
                # remaining state transitions handled by windows

        ##print "New state:", self.state

    def setState(self, state):
        print "Transition from {} to {}".format(self.state, state)
        if state == "TIMED-WAIT" or state == "ACK-SENT":
            self.state = state
            self.closeTimer = threading.Timer(self.timeout, self.setState, args=["CLOSED"])
            self.closeTimer.start()
        elif state == "CLOSE-WAIT":
            self.state = state
            self.close()
        elif state == "CLOSED":
            if self.state == "TIMED-WAIT" or self.state == "LAST-ACK":
                self.recvWindow.allReceived.wait(self.timeout)
                self.sendWindow.allACKed.wait(self.timeout)
                self.recvWindow = None
                self.sendWindow = None
            elif self.state == "ACK-SENT":
                self.sendFIN(self.sequenceNumber)

            if self.parentConnection is None and self.activeConnections is not None:
                """ Original server connection
                """
                for address in self.activeConnections:
                    activeConnections.close()
                self.listeningFlag.set()
                self.socket.close()
            elif self.parentConnection is not None:
                """ Connection spawned by original connection
                """
                parent = self.parentConnection
                if self.destinationAddress in parent.activeConnections:
                    parent.activeConnections.pop(self.destinationAddress, None)
            else:
                """ Client connection
                """
                self.listeningFlag.set()
                self.socket.close() 
            self.closeLock.set()
            self.state = state
        else:
            self.state = state

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
        return self.socket.sendto(message.generateBytearray(), (self.destinationAddress[0], 5000)) - 8

    def sendSYN(self, sequenceNumber):
        if not self.address:
            self.bindToTempAddress()

        rxpMessage = self.generateSkeletonMessage()
        rxpMessage.sequenceNumber = sequenceNumber
        rxpMessage.ackNumber = 0
        rxpMessage.synFlag = True
        self.sendMessage(rxpMessage)
        return rxpMessage

    def sendSYNACK(self, sequenceNumber, ackNumber):
        rxpMessage = self.generateSkeletonMessage()
        rxpMessage.sequenceNumber = sequenceNumber
        rxpMessage.ackNumber = ackNumber
        rxpMessage.synFlag = True
        rxpMessage.ackFlag = True
        self.sendMessage(rxpMessage)
        return rxpMessage

    def sendACK(self, sequenceNumber, ackNumber):
        rxpMessage = self.generateSkeletonMessage()
        rxpMessage.sequenceNumber = sequenceNumber
        rxpMessage.ackNumber = ackNumber
        rxpMessage.ackFlag = True
        self.sendMessage(rxpMessage)
        return rxpMessage

    def sendNACK(self, sequenceNumber, nackNumber):
        rxpMessage = self.generateSkeletonMessage()
        rxpMessage.sequenceNumber = 0
        rxpMessage.ackNumber = nackNumber
        rxpMessage.nackFlag = True
        self.sendMessage(rxpMessage)
        return rxpMessage

    def sendFIN(self, sequenceNumber):
        rxpMessage = self.generateSkeletonMessage()
        rxpMessage.sequenceNumber = sequenceNumber
        rxpMessage.finFlag = True
        self.sendMessage(rxpMessage)
        return rxpMessage

    def sendFINACK(self, sequenceNumber, ackNumber):
        rxpMessage = self.generateSkeletonMessage()
        rxpMessage.sequenceNumber = sequenceNumber
        rxpMessage.ackNumber = ackNumber
        rxpMessage.nackFlag = True
        rxpMessage.finFlag = True
        self.sendMessage(rxpMessage)
        return rxpMessage

    def generateSkeletonMessage(self):
        rxpMessage = RxPMessage()
        rxpMessage.sourcePort = self.address[1]
        rxpMessage.destPort = self.destinationAddress[1]
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
        self.synFlag = False
        self.ackFlag = False
        self.nackFlag = False
        self.finFlag = False
        self.checksum = 0
        self.data = bytearray()

        self.acked = False
        self.sent = False
        self.resendTimer = None

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

    def __str__(self):
        return "SRC: {}, DST: {}, SEQ: {}, ACK: {}, SYN: {}, ACK: {}, NACK: {}, FIN: {}, CHECKSUM: {}, DATA: {}".format(self.sourcePort,
                                                                                              self.destPort,
                                                                                              self.sequenceNumber,
                                                                                              self.ackNumber,
                                                                                              self.synFlag,
                                                                                              self.ackFlag,
                                                                                              self.nackFlag,
                                                                                              self.finFlag,
                                                                                              self.checksum,
                                                                                              str(self.data))

    def shorthand(self):
        if self.isSYN():
            return "SYN {}".format(self.sequenceNumber)
        elif self.isSYNACK():
            return "SYNACK {} {}".format(self.sequenceNumber, self.ackNumber)
        elif self.isACK():
            return "ACK {}".format(self.ackNumber)
        elif self.isNACK():
            return "NACK {}".format(self.ackNumber)
        elif self.isFIN():
            return "FIN {}".format(self.sequenceNumber)
        elif self.isFINACK():
            return "FINACK {} {}".format(self.sequenceNumber, self.ackNumber)
        else:
            return "SEQ {}".format(self.sequenceNumber)

    def isSYN(self):
        return (self.synFlag and not self.ackFlag and not self.nackFlag and not self.finFlag)

    def isSYNACK(self):
        return (self.synFlag and self.ackFlag and not self.nackFlag and not self.finFlag)

    def isACK(self):
        return (not self.synFlag and self.ackFlag and not self.nackFlag and not self.finFlag)
    
    def isNACK(self):
        return (not self.synFlag and not self.ackFlag and self.nackFlag and not self.finFlag)

    def isFIN(self):
        return (not self.synFlag and not self.ackFlag and not self.nackFlag and self.finFlag)

    def isFINACK(self):
        return (not self.synFlag and self.ackFlag and not self.nackFlag and self.finFlag)

class RxPReceiveWindow:

    def __init__(self, windowSize, sequenceStart, connection):
        self.dataBuffer = bytearray()
        self.bufferLock = threading.Event()
        self.window = [None]*windowSize
        self.windowSize = windowSize
        self.startSequenceNumber = sequenceStart
        self.connection = connection
        self.allReceived = threading.Event()

    def receiveMessage(self, recvdMessage):
        """ Receives the message.
            If message is uncorrupted, places it within receiving window, sends ACK, and
            slides window if necessary.
            If message is corrupted, sends NACK and discards message.
        """
        if recvdMessage.checkIntegrity():
            print "RECEIVE {} uncorrupted".format(recvdMessage.shorthand())
            windowIndex = (recvdMessage.sequenceNumber - self.startSequenceNumber) % 256
            ##print "Placing into receive window:", recvdMessage
            ##print windowIndex
            if windowIndex < self.windowSize or windowIndex > 128:
                """Packet within window or duplicate"""
                if windowIndex < self.windowSize:
                    self.window[windowIndex] = recvdMessage
                    self.allReceived.clear()
                if windowIndex == 0:
                    self.shiftWindow()
                self.connection.sendACK(0, (recvdMessage.sequenceNumber + 1) % 256)
                print "SEND ACK", (recvdMessage.sequenceNumber + 1) % 256

                """ Closing handshake state updates
                """
                if recvdMessage.isFIN():
                    if self.connection.state == "ESTABLISHED":
                        self.connection.setState("CLOSE-WAIT")
                    elif self.connection.state == "FIN-WAIT-1":
                        self.connection.setState("CLOSING")
                    elif self.connection.state == "FIN-WAIT-2":
                        self.connection.setState("TIMED-WAIT")
                elif recvdMessage.isFINACK():
                    if self.connection.state == "FIN-WAIT-1":
                        self.connection.setState("TIMED-WAIT")
        else:
            print "RECEIVE {} corrupted".format(recvdMessage.shorthand())
            nackNumber = recvdMessage.sequenceNumber
            self.connection.sendNACK(0, nackNumber)
            print "SEND NACK", recvdMessage.sequenceNumber

    def shiftWindow(self):
        index = 0
        while index < self.windowSize and self.window[index]:
            self.dataBuffer += self.window[index].data
            index += 1
        self.window = self.window[index:] + [None]*index
        self.startSequenceNumber = (self.startSequenceNumber + index) % 256
        self.bufferLock.set()

        """ Sets the event if the buffer is clear
        """
        empty = True
        for message in self.window:
            if message is not None:
                empty = False
        if empty:
            self.allReceived.set()

    def popData(self, bufSize):
        """ Attempts to remove bufSize bytes from the data buffer
            If no data is available, the call will block until data is available
            Upon data becoming available, the call will wait 200 ms for more data before
            return bufSize bytes
        """
        toSleep = not self.bufferLock.isSet()
        self.bufferLock.wait()
        if toSleep:
            time.sleep(0.2)
        bufSize = max(bufSize, len(self.dataBuffer))
        data = self.dataBuffer[:bufSize]
        self.dataBuffer = self.dataBuffer[bufSize:]
        if len(self.dataBuffer) == 0:
            self.bufferLock.clear()
        return data

class RxPSendWindow:
    def __init__(self, windowSize, sequenceStart, connection, timeout=10):
        self.messageBuffer = []
        self.windowSize = windowSize
        self.startSequenceNumber = sequenceStart
        self.timeout = timeout
        self.connection = connection
        self.allACKed = threading.Event()

    def addMessage(self, message):
        """ Add a message to the message buffer and
            send it if it falls within the window
        """
        self.messageBuffer.append(message)
        self.allACKed.clear()
        ##print "Adding message to send buffer"
        self.sendWindow()

    def sendMessage(self, message):
        """ Sends the message and begins/resets a resend timeout timer
        """
        self.connection.sendMessage(message)
        message.sent = True
        print "SEND", message.shorthand()
        if message.resendTimer:
            message.resendTimer.cancel()
        message.resendTimer = threading.Timer(self.timeout, self.sendMessage, args=[message])
        message.resendTimer.setDaemon(True)
        message.resendTimer.start()

        """ Closing handshake state updates
        """
        if message.isFIN():
            if self.connection.state == "ESTABLISHED":
                self.connection.setState("FIN-WAIT-1")
            elif self.connection.state == "CLOSE-WAIT":
                self.connection.setState("LAST-ACK")
    
    def receiveMessage(self, recvdMessage):
        """ Receives either an ACK or a NACK message
            If ACK, marks the message as ACKED and slides window if necessary
            If NACK, resends the message
        """
        if recvdMessage.checkIntegrity():
            print "RECEIVE", recvdMessage.shorthand()
            if recvdMessage.isACK():
                windowIndex = (recvdMessage.ackNumber - self.startSequenceNumber - 1) % 256
                if windowIndex >= 0 and windowIndex < self.windowSize:
                    message = self.messageBuffer[windowIndex]
                    message.acked = True

                    message.resendTimer.cancel()

                    if windowIndex == 0:
                        self.slideWindow()

                    """ Closing handshake state updates
                    """
                    if message.isFIN():
                        if self.connection.state == "FIN-WAIT-1":
                            self.connection.setState("FIN-WAIT-2")
                        elif self.connection.state == "CLOSING":
                            self.connection.setState("TIMED-WAIT")
                        elif self.connection.state == "LAST-ACK":
                            self.connection.setState("CLOSED")

            elif recvdMessage.isNACK():
                windowIndex = (recvdMessage.ackNumber - self.startSequenceNumber) % 256
                if windowIndex >= 0 and windowIndex < self.windowSize and not self.messageBuffer[windowIndex].acked:
                    message = self.messageBuffer[windowIndex]
                    self.sendMessage(message)

    def sendWindow(self):
        index = 0
        while index < len(self.messageBuffer) and index < self.windowSize:
            message = self.messageBuffer[index]
            if not message.sent:
                self.sendMessage(message)
            index += 1

    def slideWindow(self):
        """ Slides the window up to the next un-ACKed message
            Returns a list of messages that have been removed from the buffer
        """
        index = 0
        while index < len(self.messageBuffer) and index < self.windowSize and self.messageBuffer[index].acked :
            index += 1
        ACKed = self.messageBuffer[:index]
        self.messageBuffer = self.messageBuffer[index:]
        self.startSequenceNumber = (self.startSequenceNumber + len(ACKed)) % 256

        self.sendWindow()

        if len(self.messageBuffer) == 0:
            self.allACKed.set()

        return ACKed
