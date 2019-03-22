import asyncio
import datetime
import time
import config
import logging
import sys
from motor.motor_asyncio import AsyncIOMotorClient
from utils import CiscoSwitch, BrocadeSwitch

async def write_into_db(wwpn_item, collection):
    record = wwpn_item.copy()
    chengdu = datetime.timezone(datetime.timedelta(hours=8))
    record.update(dict(timestamp=datetime.datetime.now(chengdu).strftime('%c')))

    existed = await collection.find_one({"wwpn": record["wwpn"]})
    if existed:
        logging.info(f'update exist wwpn record {record["wwpn"]}')
        await collection.replace_one({"wwpn": record["wwpn"]}, record)
    else:
        logging.info(f'insert new record {record}')
        await collection.insert_one(record)

async def write_zones_into_db(zone_item, collect_zone):
    record = zone_item.copy()
    chengdu = datetime.timezone(datetime.timedelta(hours=8))
    record.update(dict(timestamp=datetime.datetime.now(chengdu).strftime('%c')))

    existed = await collect_zone.find_one({"zone": record["zone"]})
    if existed:
        logging.info(f'update exist zone record {record["zone"]}')
        await collect_zone.replace_one({"zone": record["zone"]}, record)
    else:
        logging.info(f'insert new record {record}')
        await collect_zone.insert_one(record)

def init_db(mongo):
    db_clinet = AsyncIOMotorClient(mongo["host"], mongo["port"])
    db = db_clinet[mongo["db"]]
    # db[mongo["collection"]].create_index([('wwpn', pymongo.ASCENDING)], unique=True)
    return (db[mongo["collection"]], db[mongo["collect_zone"]])

if __name__ == '__main__':
    collection, collect_zone = init_db(config.mongo)
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
                    asyncio.wait( [write_zones_into_db( {'zone':k, 'value':v},collect_zone) for (k,v) in i.zones_dict.items()] )
                )
                loop.run_until_complete(
                    asyncio.wait( [write_into_db(x, collection) for x in i.wwpn] )
                )
            except (ValueError, TypeError):
                logging.error(f'Failed to collect wwpn from cisco {i.ip}')

        for i in BROCADE:
            for vswitch in i.vf_data:
                try:
                    loop.run_until_complete(
                        asyncio.wait([write_into_db(x, collection) for x in vswitch.wwpn])
                    )
                    loop.run_until_complete(
                        asyncio.wait( [write_zones_into_db( {'zone':k, 'value':v},collect_zone) for (k,v) in vswitch.zones_dict.items()] )
                    )
                except (ValueError, TypeError):
                    logging.error(f'Failed to collect wwpn from brocade {vswitch.ip} -- vswitch {vswitch.fid}')
                    logging.error(f'ValueError {ValueError} \n -- TypeError {TypeError}')
        logging.info('Dumping data complete')
        time.sleep(config.interval)
