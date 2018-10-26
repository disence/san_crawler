import asyncio
import datetime
import time
from utils import CiscoSwitch, BrocadeSwitch
import config
import logging
import sys
from motor.motor_asyncio import AsyncIOMotorClient


async def write_into_db(wwpn_item, collection):
    record = wwpn_item.copy()
    chengdu = datetime.timezone(datetime.timedelta(hours=8))
    record.update(dict(timestamp=datetime.datetime.now(chengdu).strftime('%c')))

    existed = await collection.find_one({"wwpn": record["wwpn"]})
    if existed:
        await collection.replace_one({"wwpn": record["wwpn"]}, record)
    else:
        await collection.insert_one(record)


def init_db(mongo):
    db_clinet = AsyncIOMotorClient(mongo["host"], mongo["port"])
    db = db_clinet[mongo["db"]]
    # db[mongo["collection"]].create_index([('wwpn', pymongo.ASCENDING)], unique=True)
    return db[mongo["collection"]]

if __name__ == '__main__':
    collection = init_db(config.mongo)
    logging.basicConfig(
        handlers=[logging.StreamHandler(sys.stdout)],
        level=logging.INFO
    )
    loop = asyncio.get_event_loop()

    while True:
        logging.info('Pull circle Start')
        CISCO = [CiscoSwitch(*i) for i in config.cisco]
        BROCADE = [BrocadeSwitch(*i) for i in config.brocade]
        ALL = CISCO + BROCADE

        loop.run_until_complete(
            asyncio.wait([i.get_all_wwpn() for i in ALL])
        )
        logging.info('Pull circle End')
        logging.info('Dumping data to DB...')
        for i in CISCO:
            try:
                loop.run_until_complete(
                    asyncio.wait([write_into_db(x, collection) for x in i.wwpn])
                )
            except (ValueError, TypeError):
                logging.error(f'Failed to collect wwpn from {i.ip}')

        for i in BROCADE:
            for vswitch in i.vf_data:
                try:
                    loop.run_until_complete(
                        asyncio.wait([write_into_db(x, collection) for x in vswitch.wwpn])
                    )
                except (ValueError, TypeError):
                    logging.error(f'Failed to collect wwpn from vswitch {vswitch.ip} -- {vswitch.fid}')
        logging.info('Dumping data complete')
        time.sleep(config.interval)
