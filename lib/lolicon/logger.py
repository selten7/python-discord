import logging
import time

logging.Formatter.converter = time.gmtime

l = logging.getLogger('')

def disable():
    global l

    l.setLevel(100)

def enable(debug=False):
    global l

    if debug:
        logging.basicConfig(
            format='[%(asctime)s GMT] [PID=%(process)d] [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s'
        )
        l.setLevel(logging.DEBUG)
    else:
        logging.basicConfig(
            format='[%(asctime)s GMT] [%(levelname)s] %(message)s'
        )
        l.setLevel(logging.INFO)

disable()
