import unittest
import types
from lib import BrocadeSwitch, CiscoSwitch
from pull import write_into_redis, worker
import redis


@unittest.skip
class TestBrocadeSwitchMethods(unittest.TestCase):

    def setUp(self):
        self.sw = BrocadeSwitch('10.228.183.12', 'user_platform', 'password')
        self.sw.connect()

    def test_switchshow(self):
        self.assertIn('switchName', self.sw.get_switchshow())

    def test_fid_filter(self):
        self.assertEqual(
            '40',
            self.sw.filter_local_fid(self.sw.get_switchshow())
        )

    def test_switchname_filter(self):
        self.assertEqual(
            'WIN183012_BRWEDGE_PLATFORM_40',
            self.sw.filter_local_switchname(self.sw.get_switchshow())
        )

    def test_plogin(self):
        fabricshow = self.sw.get_fabricshow()
        nscamshow = self.sw.get_nscamshow()
        fabric_map = self.sw.fabric_analyze(fabricshow)
        plgin_info = self.sw.plogin_wwpn(nscamshow, fabric_map)
        self.assertTrue(isinstance(plgin_info, types.GeneratorType))

    def test_flogin(self):
        switchshow = self.sw.get_switchshow()
        flogin_info = self.sw.flogin_wwpn(switchshow)
        self.assertTrue(isinstance(flogin_info, types.GeneratorType))

    def tearDown(self):
        self.sw.disconnect()


@unittest.skip
class TestWriteIntoRedis(unittest.TestCase):

    def setUp(self):
        self.redis_client = redis.StrictRedis(
            host='localhost',
            port=32768,
            decode_responses=True,
            db=0
        )

    def test_write_a_line(self):
        write_into_redis(
            self.redis_client,
            'test_wwpn',
            '5',
            '1',
            'test_switch',
            'x.x.x.x',
            'cisco'
        )
        self.assertIn('test_wwpn', self.redis_client.keys())


class Integration(unittest.TestCase):

    def setUp(self):
        self.redis_client = redis.StrictRedis(
            host='localhost',
            port=32768,
            decode_responses=True,
            db=0
        )
        self.redis_client.flushall()
        self.b = BrocadeSwitch('10.228.183.12', 'user_platform', 'password')
        self.c = CiscoSwitch('10.228.104.13', 'emc', 'Emc12345')

    def test_brocade(self):
        worker(self.b, self.redis_client)
        self.assertTrue(self.redis_client.keys())

    def test_cisco(self):
        worker(self.c, self.redis_client)
        self.assertTrue(self.redis_client.keys())


if __name__ == '__main__':
    unittest.main()
