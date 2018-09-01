import threading
import datetime
import time
from utils import BrocadeVirtualSwitch
from config import search_scope
import logging
import sys

def worker(switch):
    if switch.vendor == 'brocade':
        switch.get_fid_list()
        switch.close()
        for fid in switch.fid_list:
            vswitch = BrocadeVirtualSwitch(
                switch.ip,
                switch.username,
                switch.password,
                fid
            )
            for wwpn in vswitch.get_all_wwpn():
                # TODO write it into MongoDB
                pass
            vswitch.close()
    elif switch.vendor == 'cisco':
        for wwpn in switch.get_all_wwpn():
            # TODO write it into MongoDB
            pass
        switch.close()

if __name__ == '__main__':
    logging.basicConfig(
        handlers=[logging.StreamHandler(sys.stdout)],
        level=logging.INFO
    )
    while True:
        logging.info('Pull circle Start')
        threads = []
        for i in search_scope:
            threads.append(threading.Thread(target=worker))

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        logging.info('Pull circle End')

        time.sleep(300)
