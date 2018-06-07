import threading
import redis
import datetime
import time
from config import search_scope
import logging
import sys


def write_into_redis(
    redis_client, wwpn, fid,
    port_index, switch_name,
    ip, vendor
):
    chengdu = datetime.timezone(datetime.timedelta(hours=8))
    redis_client.hset(wwpn, 'vsan_vf', fid)
    redis_client.hset(wwpn, 'port', port_index)
    redis_client.hset(wwpn, 'switch_name', switch_name)
    redis_client.hset(wwpn, 'switch_ip', ip)
    redis_client.hset(wwpn, 'switch_vendor', vendor)
    redis_client.hset(
        wwpn,
        'timestamp',
        datetime.datetime.now(chengdu).strftime('%c')
    )


def worker(switch, redis_client):
    if not switch.connect():
        logging.error('Failed to login to {}'.format(switch.ip))
        return False
    logging.info('Login to {} successfully.'.format(switch.ip))
    if switch.vendor == 'brocade':
        fid_list = switch.fid_filter(switch.get_fid_list())
        for fid in fid_list:
            nscamshow = switch.get_nscamshow(fid=fid)
            switchshow = switch.get_switchshow(fid=fid)
            fabricshow = switch.get_fabricshow(fid=fid)

            if switchshow:
                switch_name = switch.filter_local_switchname(switchshow)
                # handle flogin part
                flogin_wwpns = switch.flogin_wwpn(switchshow)

                for i in flogin_wwpns:
                    write_into_redis(
                        redis_client, i[0], fid, i[1], switch_name,
                        switch.ip, switch.vendor
                    )
                # handle plogin part
                if nscamshow and fabricshow:
                    fabric_map = switch.fabric_analyze(fabricshow)
                    plogin_wwpns = switch.plogin_wwpn(nscamshow, fabric_map)
                    for i in plogin_wwpns:
                        write_into_redis(
                            redis_client, i[0], fid, i[1], i[2],
                            i[3], switch.vendor
                        )
    elif switch.vendor == 'cisco':
        fcns_database = switch.get_fcns_database()
        if fcns_database:
            for i in switch.fcns_analyze(fcns_database):
                write_into_redis(redis_client, *i, switch.vendor)
    switch.close()


if __name__ == '__main__':
    r = redis.StrictRedis(
        host='redis',
        port=6379,
        db=0
    )
    logging.basicConfig(
        handlers=[logging.StreamHandler(sys.stdout)],
        level=logging.INFO
    )
    while True:
        logging.info('Pull circle Start')
        threads = []
        for i in search_scope:
            threads.append(threading.Thread(target=worker, args=(i, r)))

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        logging.info('Pull circle End')

        time.sleep(300)
