import re
import paramiko
import logging


class SSHClient():
    def __init__(self, ip, username, password):
        self.ip = ip
        self.username = username
        self.password = password
        self.client = paramiko.client.SSHClient()
        self.client.set_missing_host_key_policy(
            paramiko.client.AutoAddPolicy()
        )

    def connect(self):
        try:
            self.client.connect(
                self.ip,
                username=self.username,
                password=self.password,
                timeout=20
            )
            return True
        except:
            logging.error('failed to connect to {}'.format(self.ip))
            return False

    def disconnect(self):
        self.client.close()


class CiscoSwitch(SSHClient):
    def __init__(self, *args):
        self.vendor = 'cisco'
        super().__init__(*args)

    def get_fcns_database(self):
        command = 'show fcns database detail'
        try:
            return self.client.exec_command(command)[1].read().decode()
        except:
            logging.info('failed to get fcns database from {}'.format(self.ip))
            return ''

    def fcns_analyze(self, fcnsdatabase):
        wwpn_pattern = re.compile(
            '(?<=port-wwn \(vendor\)           :)\w{2}(:\w{2}){7}'
        )
        vsan_pattern = re.compile('(?<=VSAN:)\d+')
        port_pattern = re.compile('(?<=connected interface         :).+')
        sw_pattern = re.compile('(?<=switch name \(IP address\)    :).+')
        ip_pattern = re.compile('\d+(\.\d+){3}')

        def search_or_default(pattern, content):
            default_value = ''
            result = pattern.search(content)
            if result:
                return result.group()
            else:
                return default_value

        for entry in re.split('-{24}(?=\nVSAN)', fcnsdatabase):
            if 'VSAN' not in entry:
                continue
            wwpn, vsan_id, port, switch = [
                search_or_default(x, entry) for x in [
                    wwpn_pattern,
                    vsan_pattern,
                    port_pattern,
                    sw_pattern
                ]
            ]
            ip_search_result = ip_pattern.search(switch)
            if ip_search_result:
                switch_ip = ip_search_result.group()
                switch_name = switch.split('(')[0].strip()
            else:
                switch_ip = ''
                switch_name = switch
            yield [wwpn, vsan_id, port, switch_name, switch_ip]


class BrocadeSwitch(SSHClient):
    def __init__(self, *args):
        self.vendor = 'brocade'
        self.get_switchshow = self.collect('switchshow')
        self.get_nscamshow = self.collect('nscamshow')
        self.get_fabricshow = self.collect('fabricshow')
        self.get_fid_list = self.collect("configshow -all | grep 'Fabric ID'")
        self.filter_local_fid = self.make_single_filter(
            '(?<=FID: )\d+',
            description="""
            filter fid from switchshow
            """
            )
        self.filter_local_switchname = self.make_single_filter(
            '(?<=switchName:).+',
            description="""
            filter switchname from switchshow
            """
            )
        self.filter_wwpn = self.make_single_filter(
            '[0-9a-z:]{2}(:[0-9a-z:]{2}){7}',
            description="""
            filter out single wwpn from content
            """
            )

        super().__init__(*args)

    def collect(self, command, description=''):
        def inner(fid=''):
            if fid:
                full_command = 'fosexec --fid {} -cmd {}'.format(fid, command)
            else:
                full_command = command
            i, o, e = self.client.exec_command(full_command)
            try:
                return o.read().decode()
            except:
                logging.info(
                    'failed to read output of {} on {}'.format(
                        full_command, self.ip
                    )
                )
                return ''
        inner.__doc__ = description
        return inner

    def make_single_filter(self, f_content, description=''):
        def inner(content):
            pattern = re.compile(f_content)
            result_obj = re.search(pattern, content)
            if result_obj:
                result = result_obj.group()
                if isinstance(result, str):
                    return result.strip()
            logging.error(
                'failed to filter {} from {}'.format(pattern, content)
            )

            return None
        inner.__doc__ = description
        return inner

    def fabric_analyze(self, fabricshow):
        """
        return a fabric map in dict for plogin part
        """
        fabric_map = dict()
        content = fabricshow.split('-\n')[-1]
        for line in content.split('\n'):
            line = line.strip()
            items = re.split('\s+', line)
            if len(items) == 6:
                fabric_map[items[1]] = dict()  # use switch ID as key
                fabric_map[items[1]]['ip'] = items[3]
                fabric_map[items[1]]['name'] = items[5].strip('>" ')
        return fabric_map

    def plogin_wwpn(self, nscamshow, fabric_map):
        """
        retrive plogin wwpn from nscam
        return a generator of wwpn info in following format:
            [
            wwpn,
            port_index,
            switch_name,
            switch_ip
            ]
        """
        switch_id_pattern = re.compile('(?<= )\w{2}(?=\w{4};)')
        wwpn_pattern = re.compile('(?<=Permanent Port Name: )\S+')
        port_index_pattern = re.compile('(?<=Port Index: )\d+')

        switch_id_list = re.findall(switch_id_pattern, nscamshow)
        wwpn_list = re.findall(wwpn_pattern, nscamshow)
        port_index_list = re.findall(port_index_pattern, nscamshow)

        length = len(switch_id_list)
        if all(len(x) == length for x in [wwpn_list, port_index_list]):
            for i in range(0, length):
                for full_id in fabric_map.keys():
                    if full_id.endswith(switch_id_list[i]):
                        break
                yield [
                    wwpn_list[i],
                    port_index_list[i],
                    fabric_map[full_id]['name'],
                    fabric_map[full_id]['ip']
                ]

    def flogin_wwpn(self, switchshow):
        """
        retrive flogin wwpn from switchshow
        return a generator of wwpn info in following format:
            [
            wwpn,
            port_index
            ]
        """
        for line in switchshow.split('===\n')[-1].split('\n'):
            if 'Online' not in line:
                continue
            port_index = line.split()[0]
            wwpn = self.filter_wwpn(line)
            if wwpn:
                yield [
                    wwpn,
                    port_index,
                ]

    def fid_filter(self, content):
        try:
            return re.findall('\d+', content)
        except:
            return []
