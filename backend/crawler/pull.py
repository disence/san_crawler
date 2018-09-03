from threading import Thread
import datetime
import time
from utils import BrocadeVirtualSwitch, CiscoSwitch, BrocadeSwitch
import config
import logging
import sys
import pymongo


def work_flow(switch, db):
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

            for x in vswitch.get_all_wwpn():
                old = db[vswitch.vendor].find_one({"wwpn": x["wwpn"]})
                if old:
                    db[vswitch.vendor].replace_one({"wwpn": x["wwpn"]}, x)
                else:
                    db[vswitch.vendor].insert_one(x)
            vswitch.close()
    elif switch.vendor == 'cisco':
        for x in switch.get_all_wwpn():
            old = db[switch.vendor].find_one({"wwpn": x["wwpn"]})
            if old:
                db[switch.vendor].replace_one({"wwpn": x["wwpn"]}, x)
            else:
                db[switch.vendor].insert_one(x)
        switch.close()

if __name__ == '__main__':
    db_clinet = pymongo.MongoClient(config.mongo["host"], config.mongo["port"])
    db = db_clinet.wwpn_records
    db.cisco.create_index([('wwpn', pymongo.ASCENDING)], unique=True)
    db.brocade.create_index([('wwpn', pymongo.ASCENDING)], unique=True)

    logging.basicConfig(
        handlers=[logging.StreamHandler(sys.stdout)],
        level=logging.INFO
    )

    while True:
        logging.info('Pull circle Start')
        threads = []
        for i in config.cisco:
            threads.append(Thread(target=work_flow, args=(CiscoSwitch(*i), db)))
        for i in config.brocade:
            threads.append(Thread(target=work_flow, args=(BrocadeSwitch(*i), db)))

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        logging.info('Pull circle End')

        time.sleep(config.interval)
