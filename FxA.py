import sys
import re

def get_arguments():
    argv = sys.argv
    if len(argv) < 4:
        print "Invalid invocation. Include listening port number, NetEmu IP, and NetEmu port number"
        sys.exit()

    command, listening_port, netemu_ip, netemu_port = argv

    try:
        listening_port = int(listening_port)
    except ValueError:
        print "Invalid invocation. Listening port number must be an integer"
        sys.exit()

    m = re.search('^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$', netemu_ip)
    if m is None:
        print "Invalid invocation. Netemu IP must be IPv4 address"
        sys.exit()

    try:
        netemu_port = int(netemu_port)
    except ValueError:
        print "Invalid invocation. Netemu port number must be an integer"
        sys.exit()

    return (command, listening_port, netemu_ip, netemu_port)

def make_message(message_type, message):
    length = len(message)
    parts = [message_type, length, message]
    message = ":".join([str(part) for part in parts])
    return message

def read_message(socket):
    data = socket.recv(1024)
    if data is None:
        print "got None data"
        return None, None
    command, arg_length, data = data.split(":", 2)
    command = str(command)
    arg_length = int(arg_length)
    print "got command {} and arg_length {} now reading data".format(command, arg_length)
    while arg_length - len(data) > 0:
        data += socket.recv(arg_length - len(data))
        print "{} bytes left".format(arg_length-len(data))
    return command, data
