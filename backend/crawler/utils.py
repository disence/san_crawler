import re
import logging
import asyncssh
from itertools import chain


class CiscoSwitch():
    def __init__(self, ip, username, password):
        self.vendor = 'cisco'
        self.fcns = ''
        self.ip = ip
        self.username = username
        self.password = password
        self.session = None
        self.wwpn = None
        self.node_symb = '',
        self.link_speed = '',

    def _analyze_record(self):
        wwpn_pattern = r'\w{2}(:\w{2}){7}'
        for raw in re.split('-{24}(?=\nVSAN)', self.fcns):
            record = dict(
                switch_vendor=self.vendor,
                switch_ip='',
                switch_name='',
                port='',
                vsan='',
                wwpn='',
                node_symb='',
                link_speed='',
            )
            if 'VSAN' not in raw:
                continue
            for line in raw.split('\n'):
                if line.startswith('port-wwn'):
                    try:
                        record.update(wwpn=re.search(wwpn_pattern, line).group())
                    except AttributeError:
                        # no wwpn means no record
                        break

                elif 'VSAN:' in line:
                    record.update(vsan=line.split(':')[1].split()[0])
                elif 'connected interface' in line:
                    record.update(port=line.split(':')[-1].strip())
                elif 'switch name (IP address)' in line:
                    switch_name_and_ip = line.split(':')[-1].strip()
                    if '(' in switch_name_and_ip:
                        record.update(switch_ip=switch_name_and_ip.split('(')[-1].split(')')[0])
                        record.update(switch_name=switch_name_and_ip.split('(')[0].strip())
                    else:
                        record.update(switch_ip='')
                        record.update(switch_name=switch_name_and_ip)
                elif 'symbolic-port-name' in line:
                    record.update(node_symb=line.split(':')[-1].strip())
                elif 'Device Link speed' in line:
                    record.update(link_speed=line.split(':')[-1].strip())
            if record.get('wwpn'):
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

class BrocadeSwitch():
    def __init__(self, ip, username, password):
        self.ip = ip
        self.username = username
        self.password = password
        self.session = None
        self.vendor = 'brocade'
        self.vf_list = list()
        self.vf_data = list()
    async def _get_command_output(self, command, vf):
        command = f'fosexec --fid {vf} -cmd {command}'
        try:
            result = await self.session.run(command)
            if result.stdout:
                return result.stdout
        except asyncssh.Error as e:
            logging.error(e)
        return ''

    async def _get_switchshow(self, vf):
        return await self._get_command_output('switchshow', vf)

    async def _get_nscamshow(self, vf):
        return await self._get_command_output('nscamshow', vf)

    async def _get_fabricshow(self, vf):
        return await self._get_command_output('fabricshow', vf)

    async def _get_vf_list(self):
        possible_cmd = [
            "configshow -all | grep 'Fabric ID'",
            "configshow | grep 'Fabric ID'",
        ]
        for cmd in possible_cmd:
            try:
                result = await self.session.run(cmd)
                if result.stdout:
                    self.vf_list += re.findall(r'\d+', result.stdout)
            except asyncssh.Error as e:
                logging.error(e)

    async def get_all_wwpn(self):
        async with asyncssh.connect(
            self.ip,
            username=self.username,
            password=self.password,
            known_hosts=None
        ) as self.session:
            await self._get_vf_list()
            for vf in self.vf_list:
                self.vf_data.append(
                    BrocadeVF(
                        self.ip,
                        vf,
                        nscamshow=await self._get_nscamshow(vf),
                        switchshow=await self._get_switchshow(vf),
                        fabricshow=await self._get_fabricshow(vf)
                    )
                )

class BrocadeVF():
    def __init__(self, ip, vf, nscamshow='', switchshow='', fabricshow=''):
        self.ip = ip
        self.vendor = 'brocade'
        self.fid = vf
        self.nscamshow = nscamshow
        self.switchshow = switchshow
        self.fabricshow = fabricshow
        self.switchname = ''
        self.fabricmap = list()
        self.wwpn_pattern = r'\w{2}(:\w{2}){7}'
        self._get_switchname()
        self._get_fabricmap()
        self.flogin_wwpn = self.get_flogin_wwpn()
        self.plogin_wwpn = self.get_plogin_wwpn()
        self.wwpn = chain( self.flogin_wwpn, self.plogin_wwpn)
        self.node_symb = ''
        self.link_speed = ''

    def _get_switchname(self):
        for line in self.switchshow.split("\n"):
            if line.startswith('switchName:'):
                self.switchname = line.split(":")[-1].strip()

    def _get_fabricmap(self):
        for line in self.fabricshow.split('-\n')[-1].split('\n'):
            if ':' in line:
                items = line.split()
                if len(items) == 6:
                    self.fabricmap.append(
                        dict(
                            switch_id=items[1],
                            switch_ip=items[3],
                            switch_name=items[5].strip('>" ')
                        )
                    )

    def get_plogin_wwpn(self):
        """
        Example of the nscamshow:
            N    172a07;    2,3;c0:50:76:05:09:6b:00:66;c0:50:76:05:09:6b:00:66;
                Fabric Port Name: 20:2e:00:05:33:69:62:02
                Permanent Port Name: 10:00:00:00:c9:a1:82:bd
                Port Index: 46
                Share Area: No
                Device Shared in Other AD: No
                Redirect: No
                Partial: No
            N    172a08;    2,3;c0:50:76:05:09:6b:00:72;c0:50:76:05:09:6b:00:72;
                Fabric Port Name: 20:2e:00:05:33:69:62:02
                Permanent Port Name: 10:00:00:00:c9:a1:82:bd
                Port Index: 46
                Share Area: No
                Device Shared in Other AD: No
                Redirect: No
                Partial: No
        """
        if not self.fabricmap:
            yield dict()
        else:
            for n in self.nscamshow.split("\n"):
                if re.match(r"\s+N\s+", n):
                    (fc_id, _, wwpn, *__) = n.split(";")
                    switch_id = fc_id.split()[1][0:2]
                    for i in self.fabricmap:
                        if i["switch_id"].endswith(switch_id):
                            break
                if "NodeSymb:" in n:
                    node_symb = n.split(":")[1].strip()
                if "Port Index:" in n:
                    port_index = re.search(r"\d+", n).group()
                if "Device Link speed:" in n:
                    speed = n.split(":")[1].strip()
                    yield dict(
                        port_index=port_index,
                        node_symb=node_symb,
                        link_speed=speed,
                        wwpn=wwpn,
                        switch_name=i["switch_name"],
                        switch_ip=i["switch_ip"],
                        fid=self.fid,
                        switch_vendor=self.vendor
                    )

    def get_flogin_wwpn(self):
        """
        retrive flogin wwpn from switchshow
        """
        for line in self.switchshow.split('===\n')[-1].split('\n'):
            if 'Online' not in line:
                continue
            port_index = line.split()[0]
            wwpn_search = re.search(self.wwpn_pattern, line)
            if wwpn_search:
                yield dict(
                    switch_vendor=self.vendor,
                    switch_ip=self.ip,
                    switch_name=self.switchname,
                    port_index=port_index,
                    fid=self.fid,
                    wwpn=wwpn_search.group(),
                    node_symb=self.node_symb,
                    link_speed=self.link_speed,
                )
