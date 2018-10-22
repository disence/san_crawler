import re
import logging
import asyncssh


class CiscoSwitch():
    def __init__(self, ip, username, password):
        self.vendor = 'cisco'
        self.fcns = ''
        self.ip = ip
        self.username = username
        self.password = password
        self.session = None
        self.wwpn = None

    def _analyze_record(self):
        wwpn_pattern = r'\w{2}(:\w{2}){7}'
        record = dict(switch_vendor=self.vendor)
        for raw in re.split('-{24}(?=\nVSAN)', self.fcns):
            if 'VSAN' not in raw:
                continue
            for line in raw.split('\n'):
                if line.startswith('port-wwn'):
                    try:
                        record.update(wwpn=re.search(wwpn_pattern, line).group())
                    except AttributeError:
                        # no wwpn means no record
                        return {}

                elif 'VSAN:' in line:
                    record.update(vsan=line.split(':')[1].split()[0])
                elif 'connected interface' in line:
                    record.update(port=line.split(':')[-1].strip())
                elif 'switch name (IP address)' in line:
                    switch_name_and_ip = line.split(':')[-1].strip()
                    if '(' in switch_name_and_ip:
                        record.update(switch_ip=switch_name_and_ip.split('(')[-1].split(')')[0])
                        record.update(switchname=switch_name_and_ip.split('(')[0].strip())
                    else:
                        record.update(switch_ip='')
                        record.update(switch_name=switch_name_and_ip)
            yield record

    async def _get_fcns_database(self):
        """
        This function dumps fcns databse from the Cisco Switch.
        """
        command = 'show fcns database detail'
        try:
            result = await self.session.run(command)
            self.fcns = result.stdout
        except asyncssh.Error as e:
            logging.error(e)

    async def get_all_wwpn(self):
        """
        This function analyzes fcns database and retuns a generator which yield
        a dict once a time for each WWPN discovered in the fabric.
        """
        async with asyncssh.connect(self.ip, username=self.username, password=self.password, known_hosts=None) as self.session:
            await self._get_fcns_database()
        self.wwpn = self._analyze_record()
