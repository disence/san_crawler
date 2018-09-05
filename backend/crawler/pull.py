from threading import Thread
import datetime
import time
from utils import BrocadeVirtualSwitch, CiscoSwitch, BrocadeSwitch
import config
import logging
import sys
import pymongo


def work_flow(switch, collection):

    def _write_into_db(wwpn_item, collection):
        chengdu = datetime.timezone(datetime.timedelta(hours=8))
        wwpn_item.update(dict(timestamp=datetime.datetime.now(chengdu).strftime('%c')))

        existed = collection.find_one({"wwpn": wwpn_item["wwpn"]})
        if existed:
            collection.replace_one({"wwpn": wwpn_item["wwpn"]}, wwpn_item)
        else:
            collection.insert_one(wwpn_item)

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
                _write_into_db(x, collection)
            vswitch.close()
    elif switch.vendor == 'cisco':
        for x in switch.get_all_wwpn():
            _write_into_db(x, collection)
        switch.close()

def init_db(mongo):
    db_clinet = pymongo.MongoClient(mongo["host"], mongo["port"])
    db = db_clinet[mongo["db"]]
    db[mongo["collection"]].create_index([('wwpn', pymongo.ASCENDING)], unique=True)
    return db[mongo["collection"]]

if __name__ == '__main__':
    collection = init_db(config.mongo)
    logging.basicConfig(
        handlers=[logging.StreamHandler(sys.stdout)],
        level=logging.INFO
    )

    while True:
        logging.info('Pull circle Start')
        threads = []
        for i in config.cisco:
            threads.append(Thread(target=work_flow, args=(CiscoSwitch(*i), collection)))
        for i in config.brocade:
            threads.append(Thread(target=work_flow, args=(BrocadeSwitch(*i), collection)))

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        logging.info('Pull circle End')

        time.sleep(config.interval)
