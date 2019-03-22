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
        self.node_symb = ''
        self.link_speed = ''
        self.device_alias = {}
        self.zones_dict = {}

    def get_KeysByValue(self, valueToFind):
        listOfKeys = list()
        dictOfElements = self.zones_dict
        listOfItems = dictOfElements.items()
        for item in listOfItems:
            if ( ' '.join(item[1]) ).find(valueToFind) > 0:
                listOfKeys.append(item[0])
        return  listOfKeys

    def _analyze_record(self):
        '''
            ------------------------
            VSAN:1     FCID:0x050000
            ------------------------
            port-wwn (vendor)           :10:00:00:2a:6a:b9:cf:31 (Cisco)     
            node-wwn                    :20:00:00:2a:6a:b9:cf:30
            class                       :2,3
            node-ip-addr                :0.0.0.0
            ipa                         :ff ff ff ff ff ff ff ff
            fc4-types:fc4_features      :ipfc 
            symbolic-port-name          :
            symbolic-node-name          :
            port-type                   :N 
            port-ip-addr                :0.0.0.0
            fabric-port-wwn             :20:00:00:2a:6a:b9:cf:32
            hard-addr                   :0x000000
            permanent-port-wwn (vendor) :00:00:00:00:00:00:00:00             
            connected interface         :vsan1 (sup-fc0)
            switch name (IP address)    :E2E05-CL4-9940-102AD-V25 (10.228.99.40)
        '''
        wwpn_pattern = r'\w{2}(:\w{2}){7}'
        wwpn_to_alias = { val:key for (key,val) in self.device_alias.items()}
        for raw in re.split('-{24}(?=\nVSAN)', self.fcns):
            record = dict(
                timestamp='',
                switch_vendor=self.vendor,
                switch_ip='',
                switch_name='',
                port='',
                vsan='',
                wwpn='',
                node_symb='',
                link_speed='',
                alias_name='',
                zones=[],
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
                record.update( alias_name=wwpn_to_alias.get(record.get('wwpn'),'') )
                record.update( zones=self.get_KeysByValue(record.get('wwpn')) )
                yield record

    async def _get_command_output(self, command):
        command = f"{command}"
        try:
            result = await self.session.run(command)
            if result.stdout:
                return result.stdout
        except asyncssh.Error as e:
            logging.error(e)
        return ''

    async def _get_alias_database(self):
        """
        Returns dictionary with alias name as key and it's members as values.
        device-alias name Alias_test pwwn 10:00:00:00:00:00:00:12
        device-alias name A_HUS110_0A pwwn 50:06:0e:80:10:5b:5f:50
        """
        aliases = {}
        output = await self._get_command_output(f'show device-alias database')
        if output and not re.search('does not exist', output, re.IGNORECASE):
            alias_regex = re.compile('device-alias (.*)')
            wwpn_regex = re.compile(r'\w{2}(:\w{2}){7}')

            for line in output.split('\n'):
                line = line.strip()
                if alias_regex.search(line) and wwpn_regex.search(line):
                    content = alias_regex.search(line).group(1).split(' ')
                    if content[1] and content[3]:
                        aliases[f'{content[1]}'] = content[3]
            return aliases

    async def _get_fcns_database(self):
        """
        This function dumps fcns databse from the Cisco Switch.
        """
        return await self._get_command_output(f'show fcns database detail')

    async def _get_zones(self, alias):
        """
        Returns dictionary with zone name as key and it's members as values.
        zone name Z_temp_host25 vsan 25
        pwwn 10:00:00:00:00:00:00:25 [temp_host25]

        zone name E2E_L4_10050_HBA0_P1_FNM3252_SPAB_P1_2 vsan 25
        device-alias H_E2E_L4_10050_HBA0_P1
        device-alias A_FNM3252_SPA1_2
        """
        t_zones = {}
        output = await self._get_command_output(f'show zone')

        if output and not re.search('does not exist', output, re.IGNORECASE):
            zone_regex = re.compile('zone(.*)')
            alias_regex = re.compile('device-alias(.*)')
            zone_key = None
            zone_values = []

            for line in output.split('\n'):
                line = line.strip()
                if zone_regex.search(line):
                    content = zone_regex.search(line).group(1).split()
                    zone_key = content[1]
                    zone_values = []
                elif zone_key and alias_regex.search(line):
                    device = alias_regex.search(line).group(1).strip()
                    zone_values.append( device +' => '+ alias.get(device,'NA') )
                if zone_key and zone_values:
                    t_zones[zone_key] = zone_values
            return t_zones

    async def get_all_wwpn(self):
        """
        This function analyzes fcns database and retuns a generator which yield
        a dict once a time for each WWPN discovered in the fabric.
        """
        async with asyncssh.connect(
            self.ip,
            username=self.username,
            password=self.password,
            known_hosts=None,
        ) as self.session:
            self.fcns = await self._get_fcns_database()
            self.device_alias = await self._get_alias_database()
            self.zones_dict = await self._get_zones(self.device_alias)
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
        command = f'fosexec --fid {vf} -cmd "{command}"'
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
    
    async def _get_aliShow(self, vf, pattern='*'):
        """
        Returns dictionary with alias name as key and it's members as values. pattern '*' will return all alias
        """
        aliases = {}
        output = await self._get_command_output(f'aliShow {pattern}', vf)
        if output and not re.search('does not exist', output, re.IGNORECASE):
            alias_regex = re.compile('alias:(.*)')
            wwpn_regex = re.compile(r'\w{2}(:\w{2}){7}')
            alias_key = None
            content = False

            for line in output.split('\n'):
                line = line.strip()
                if alias_regex.search(line):
                    alias_key = alias_regex.search(line).group(1).strip()
                    content = True
                elif content and wwpn_regex.search(line) and alias_key:
                    aliases[alias_key] = wwpn_regex.search(line).group()
            return aliases

    async def _get_zoneShow(self, vf, alias_to_wwpn, pattern='*'):
        """
        Returns dictionary with zone name as key and it's members as values.
        """
        zones = {}
        output = await self._get_command_output(f'zoneShow {pattern}', vf)

        if output and not re.search('does not exist', output, re.IGNORECASE):
            zone_regex = re.compile('zone:(.*)')
            wwpn_regex = re.compile(r'\w{2}(:\w{2}){7}')
            zone_key = None
            zone_values = []

            for line in output.split('\n'):
                line = line.strip()
                if zone_regex.search(line):
                    zone_key = zone_regex.search(line).group(1).strip()
                    zone_values = []
                elif zone_key and line:
                    items = [x.strip() for x in line.split(';') if x]
                    if items:
                        for i in items:
                            # if wwpn_regex.search(i): #when no alias name exist
                            #     zone_values.append(i)
                            # else:
                            zone_values.append( i +' => '+ alias_to_wwpn.get(i,'NA') )
                if zone_key and zone_values:
                    zones[zone_key] = zone_values
            return zones

    async def get_all_wwpn(self):
        async with asyncssh.connect(
            self.ip,
            username=self.username,
            password=self.password,
            known_hosts=None,
        ) as self.session:
            await self._get_vf_list()
            for vf in self.vf_list:
                alias_to_wwpn = await self._get_aliShow(vf)
                wwpn_to_alias = {val:key for (key,val) in alias_to_wwpn.items()}
                self.vf_data.append(
                    BrocadeVF(
                        self.ip,
                        vf,
                        alias=wwpn_to_alias,
                        zones_dict=await self._get_zoneShow(vf, alias_to_wwpn),
                        nscamshow=await self._get_nscamshow(vf),
                        switchshow=await self._get_switchshow(vf),
                        fabricshow=await self._get_fabricshow(vf),  
                    )
                )

class BrocadeVF():
    def __init__(self, ip, vf, alias, zones_dict, nscamshow='', switchshow='', fabricshow=''):
        self.ip = ip
        self.vendor = 'brocade'
        self.fid = vf
        self.alias = alias
        self.zones_dict = zones_dict
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
        self.alias_name = ''
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

    def get_KeysByValue(self, valueToFind):
        listOfKeys = list()
        dictOfElements = self.zones_dict
        listOfItems = dictOfElements.items()
        for item in listOfItems:
            if ( ' '.join(item[1]) ).find(valueToFind) > 0:
                listOfKeys.append(item[0])
        return  listOfKeys

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
                    (fc_id, _, t_wwpn, *__) = n.split(";")
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
                    alias_name=self.alias.get(t_wwpn)
                    yield dict(
                        timestamp='',
                        switch_vendor=self.vendor,
                        switch_ip=i["switch_ip"],
                        switch_name=i["switch_name"],
                        port_index=port_index,
                        fid=self.fid,
                        wwpn=t_wwpn,
                        alias_name=alias_name,
                        node_symb=node_symb,
                        link_speed=speed,
                        zones=self.get_KeysByValue(t_wwpn),
                    )

    def get_flogin_wwpn(self):
        """
        retrive flogin wwpn from switchshow output
        
        Index Port Address  Media Speed   State       Proto
        ==================================================
        4   4   120000   id    N16	  Online      FC  F-Port  10:00:e4:11:5b:a7:51:b5 
        5   5   120100   id    N16	  No_Sync     FC  Disabled (Port Throttled)

        Index Slot Port Address Media  Speed        State    Proto
        ============================================================
        60    4   12   01f0c0   id    N16	  Online      FC  E-Port  10:00:c4:f5:7c:39:66:e2 "E2E25_BL4_242107_106AB-H1-SW3" (downstream)
        61    4   13   01f080   id    N16	  Online      FC  E-Port  10:00:c4:f5:7c:39:75:70 "E2E26_BL4_242108_106AB-H1-SW4" (downstream）

        """      
        header = self.switchshow.split('===\n')[0].split('\n')[-2]
        if 'Index' not in header:
            logging.error('failed to parse switchshow output detail')

        for line in self.switchshow.split('===\n')[-1].split('\n'):
            if 'Online' not in line:
                continue
            if 'Slot' in header:
                port_index = f'{line.split()[1]}/{line.split()[2]}'
            else:
                port_index = line.split()[1]
            wwpn_search = re.search(self.wwpn_pattern, line)
            t_wwpn = wwpn_search.group()
            if wwpn_search:
                yield dict(
                    timestamp='',
                    switch_vendor=self.vendor,
                    switch_ip=self.ip,
                    switch_name=self.switchname,
                    port_index=port_index,
                    fid=self.fid,
                    wwpn=t_wwpn,
                    alias_name=self.alias.get(t_wwpn),
                    node_symb=self.node_symb,
                    link_speed=self.link_speed,
                    zones=self.get_KeysByValue(t_wwpn),
                )
